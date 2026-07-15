"""MCP exposure layer (ARCHITECTURE §3; REQ-MCP-*).

A thin adapter over :class:`~mockworld.engine.Engine`, built on the official MCP
SDK's low-level ``Server`` (tools are dynamic — loaded from YAML — so the
decorator-per-tool FastMCP model doesn't fit; ADR-1). Each mock tool becomes one
MCP tool. Session identity is resolved from MCP itself — the ``Mcp-Session-Id``
header under Streamable HTTP, a single implicit session under stdio (ADR-2) — and
never invented here. W3C ``traceparent`` is read from HTTP headers or the MCP
request ``_meta`` for trace nesting (REQ-OBS-2).
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.server import request_ctx

from .engine import STDIO_SESSION, Engine
from .schema import ToolDef

_JSON_TYPES = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}


def _input_schema(tool: ToolDef) -> dict[str, Any]:
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, spec in tool.params.items():
        prop: dict[str, Any] = {"type": _JSON_TYPES[spec.type]}
        if spec.enum:
            prop["enum"] = spec.enum
        props[name] = prop
        if spec.required and spec.default is None:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


class MockServer:
    """Wraps an engine as an MCP server over stdio or Streamable HTTP."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.server: Server = Server(f"mockworld.{engine.definition.name}")
        self._register()

    # -- session / trace resolution from the MCP request context -----------------

    @staticmethod
    def _request_context():
        try:
            return request_ctx.get()
        except LookupError:
            return None

    def _session_key(self) -> str:
        rc = self._request_context()
        if rc is None:
            return STDIO_SESSION
        req = getattr(rc, "request", None)
        if req is not None and hasattr(req, "headers"):
            sid = req.headers.get("mcp-session-id")
            if sid:
                return sid
        if req is None:  # stdio: one implicit session
            return STDIO_SESSION
        return f"sess-{id(rc.session)}"

    def _traceparent(self) -> str | None:
        rc = self._request_context()
        if rc is None:
            return None
        req = getattr(rc, "request", None)
        if req is not None and hasattr(req, "headers"):
            tp = req.headers.get("traceparent")
            if tp:
                return tp
        meta = getattr(rc, "meta", None)
        if meta is not None:
            tp = getattr(meta, "traceparent", None)
            if tp:
                return tp
            extra = getattr(meta, "model_extra", None) or {}
            if extra.get("traceparent"):
                return extra["traceparent"]
        return None

    # -- MCP handlers ------------------------------------------------------------

    def _register(self) -> None:
        @self.server.list_tools()
        async def list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name=t.name,
                    description=t.description.strip(),
                    inputSchema=_input_schema(t),
                )
                for t in self.engine.definition.tools
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
            result = self.engine.call(
                name,
                arguments,
                session_id=self._session_key(),
                traceparent=self._traceparent(),
            )
            if result.success:
                data = result.data
                return data if isinstance(data, dict) else {"result": data}
            # Business fault → structured, agent-legible error (REQ-RT-11).
            payload = result.err.to_payload()
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(payload))],
                isError=True,
            )

    def init_options(self):
        return self.server.create_initialization_options()

    # -- transports --------------------------------------------------------------

    async def run_stdio(self) -> None:
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read, write):
            await self.server.run(read, write, self.init_options())

    def asgi_app(self, json_response: bool = False, control: bool = True):
        """A Starlette app serving this mock over Streamable HTTP at ``/mcp``.

        With ``control=True`` the out-of-band control plane is mounted at
        ``/control/*`` on the same server so ``mockworld reset`` can reach it,
        while remaining a distinct surface from the agent-facing ``/mcp`` (REQ-CTL-2).
        """
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from starlette.applications import Starlette
        from starlette.routing import Mount

        manager = StreamableHTTPSessionManager(app=self.server, json_response=json_response)

        async def handle(scope, receive, send):
            await manager.handle_request(scope, receive, send)

        @contextlib.asynccontextmanager
        async def lifespan(app):
            async with manager.run():
                yield

        routes = [Mount("/mcp", app=handle)]
        if control:
            from .control import control_routes

            routes.extend(control_routes(self.engine))
        return Starlette(routes=routes, lifespan=lifespan)

    def run_http(self, host: str = "127.0.0.1", port: int = 8931) -> None:
        import uvicorn

        uvicorn.run(self.asgi_app(), host=host, port=port, log_level="warning")
