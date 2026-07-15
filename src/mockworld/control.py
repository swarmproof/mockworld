"""Control plane + stampede Target protocol (ARCHITECTURE §7; REQ-CTL-*, REQ-STAMP-5).

The control plane is deliberately separate from the agent-facing MCP surface
(REQ-CTL-2): agents call tools; an operator (or stampede) drives reset/seed/
faults/snapshots out of band. ``MockworldTarget`` implements the full stampede
``Target`` protocol so a stampede swarm can boot, drive, and reset a mockworld
world deterministically. stampede is not a dependency, so protocol values are
plain dicts/dataclasses matching the agreed shapes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .engine import STDIO_SESSION, Engine


class ControlAPI:
    """In-process control surface; also mountable as an HTTP app (below)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def boot(self, seed: int, faults: str | dict = "realistic") -> dict[str, Any]:
        self.engine.reset(seed)
        self.engine.set_faults(faults)
        return {
            "mock": self.engine.definition.name,
            "seed": seed,
            "session_policy": "per_session_overlay",
        }

    def reset(self, seed: int | None = None) -> None:
        self.engine.reset(seed)

    def set_faults(self, config: str | dict) -> None:
        self.engine.set_faults(config)

    def session_reset(self, session_id: str) -> None:
        self.engine.session_reset(session_id)

    def snapshot(self, path: str, session_id: str = STDIO_SESSION) -> str:
        """Serialize a session's state to a portable artifact (REQ-SNAP-1)."""
        self.engine.store.persist(session_id, path)
        return path

    def restore(self, path: str, session_id: str = STDIO_SESSION) -> None:
        self.engine.store.restore(session_id, path)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "mock": self.engine.definition.name,
            "version": self.engine.definition.version,
            "seed": self.engine.seed,
            "sessions": self.engine.sessions.count(),
        }


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: dict | None = None
    fault: dict | None = None


class MockworldTarget:
    """Adapts an engine to stampede's ``Target`` protocol (REQ-STAMP-5).

    Each stampede agent maps to one mockworld session, giving per-agent isolation.
    ``reset(seed)`` makes state a pure function of the seed — the single thing a
    real target can't offer, and what makes stampede runs bit-reproducible.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.control = ControlAPI(engine)

    async def discover(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description.strip(), "type": "function"}
            for t in self.engine.definition.tools
        ]

    async def invoke(self, call: dict[str, Any], ctx: dict[str, Any] | None = None) -> ToolResult:
        ctx = ctx or {}
        session_id = ctx.get("agent_id") or ctx.get("session_id") or STDIO_SESSION
        result = self.engine.call(
            call["name"],
            call.get("arguments", {}),
            session_id=session_id,
            call_id=call.get("call_id"),
            traceparent=ctx.get("traceparent"),
        )
        fault = None
        if result.meta.get("latency_ms") or (not result.success):
            span = self.engine.tracer.spans[-1]
            if span.attributes.get("swarmproof.fault.injected"):
                fault = {
                    "type": span.attributes.get("swarmproof.fault.type"),
                    "error": span.attributes.get("swarmproof.fault.error"),
                    "source": "mockworld",
                }
        if result.success:
            return ToolResult(ok=True, data=result.data, fault=fault)
        return ToolResult(ok=False, error=result.err.to_payload(), fault=fault)

    async def reset(self, seed: int | None = None) -> None:
        self.engine.reset(seed)

    async def health(self) -> dict[str, Any]:
        return self.control.health()

    def isolation(self) -> str:
        # Per-session CoW overlays → each agent gets its own tenant (stampede FR-TA-06).
        return "per_agent"

    def safety_descriptor(self) -> dict[str, Any]:
        # A mock is inherently a sandbox → stampede's Safety Gate auto-allows it.
        return {"sandboxed": True, "moves_real_money": False, "external_side_effects": False}


def control_asgi_app(engine: Engine):
    """A small Starlette app exposing the control plane over HTTP (REQ-CTL-1)."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    api = ControlAPI(engine)

    async def health(_: Request) -> JSONResponse:
        return JSONResponse(api.health())

    async def reset(request: Request) -> JSONResponse:
        body = await _json(request)
        api.reset(body.get("seed"))
        return JSONResponse({"status": "reset", "seed": engine.seed})

    async def set_faults(request: Request) -> JSONResponse:
        body = await _json(request)
        api.set_faults(body.get("faults", "realistic"))
        return JSONResponse({"status": "faults_set"})

    async def session_reset(request: Request) -> JSONResponse:
        body = await _json(request)
        api.session_reset(body["session_id"])
        return JSONResponse({"status": "session_reset"})

    async def _json(request: Request) -> dict:
        try:
            return await request.json()
        except Exception:
            return {}

    return Starlette(
        routes=[
            Route("/control/health", health, methods=["GET"]),
            Route("/control/reset", reset, methods=["POST"]),
            Route("/control/faults", set_faults, methods=["POST"]),
            Route("/control/session_reset", session_reset, methods=["POST"]),
        ]
    )
