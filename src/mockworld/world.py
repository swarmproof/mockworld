"""World composition (ROADMAP v0.2; REQ-WORLD-*).

A ``world.yaml`` composes several mocks into one MCP server that shares a seed and
a **shared identity namespace** — the same customer ids/names flow into payments,
crm, and email so an agent can refund a charge, update the matching CRM record,
and email that customer, all consistently. Tools are namespaced ``<mock>_<tool>``.

``WorldEngine`` quacks like :class:`~mockworld.engine.Engine` (``.definition`` +
``.call``) so the existing MCP server and control plane host it unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .datagen import DataGen
from .determinism import DeterministicContext
from .engine import STDIO_SESSION, Engine
from .errors import Result
from .schema import SCHEMA_VERSION, ToolDef


class WorldDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    name: str
    seed: int = 0
    mocks: list[str]
    # size of each shared identity pool, e.g. {"customers": 50}
    identity: dict[str, int] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def _v(cls, v: str) -> str:
        if str(v) != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {v!r}")
        return str(v)

    @field_validator("mocks")
    @classmethod
    def _no_underscore(cls, mocks: list[str]) -> list[str]:
        bad = [m for m in mocks if "_" in m]
        if bad:
            raise ValueError(f"mock names may not contain '_': {bad}")
        return mocks


class _WorldDefinition:
    """Minimal MockDef-shaped facade so MockServer can host a world unchanged."""

    def __init__(self, name: str, version: str, tools: list[ToolDef]) -> None:
        self.name = name
        self.version = version
        self.tools = tools

    def tool(self, name: str) -> ToolDef | None:
        return next((t for t in self.tools if t.name == name), None)


class WorldEngine:
    def __init__(
        self,
        world: WorldDef,
        *,
        seed: int | None = None,
        faults: str | dict = "realistic",
        store: str = "memory",
        run_id: str = "world",
    ) -> None:
        self.world = world
        self.seed = world.seed if seed is None else seed
        self.shared = self._build_identity_pool(self.seed)
        self.engines: dict[str, Engine] = {}
        self._route: dict[str, tuple[str, str]] = {}
        tools: list[ToolDef] = []

        for mock_name in world.mocks:
            eng = Engine.from_source(
                f"mock:{mock_name}", seed=self.seed, faults=faults, store=store,
                run_id=run_id, shared=self.shared,
            )
            self.engines[mock_name] = eng
            for t in eng.definition.tools:
                namespaced = f"{mock_name}_{t.name}"
                nt = t.model_copy(deep=True)
                nt.name = namespaced
                nt.description = f"[{mock_name}] {t.description}"
                tools.append(nt)
                self._route[namespaced] = (mock_name, t.name)

        self.definition = _WorldDefinition(world.name, "0.1.0", tools)
        self.tracer = None  # per-mock tracers live on each sub-engine

    def _build_identity_pool(self, seed: int) -> dict[str, Any] | None:
        dctx = DeterministicContext(seed)
        fake = DataGen(dctx.seed_rng())
        ids = dctx.ids_for("__world__", 0)
        pool: dict[str, Any] = {}
        for _ in range(self.world.identity.get("customers", 0)):
            name = fake.name()
            pool.setdefault("customers", []).append(
                {"id": ids.next("cus"), "name": name, "email": fake.email(name)}
            )
        return pool or None

    # -- Engine-compatible surface ----------------------------------------------

    def call(
        self,
        tool_name: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str = STDIO_SESSION,
        call_id: str | None = None,
        traceparent: str | None = None,
    ) -> Result:
        route = self._route.get(tool_name)
        if route is None:
            return Result.error("unknown_tool", f"No such world tool: {tool_name!r}")
        mock_name, real = route
        return self.engines[mock_name].call(
            real, params, session_id=session_id, call_id=call_id, traceparent=traceparent
        )

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = seed
            self.shared = self._build_identity_pool(seed)
        for eng in self.engines.values():
            eng.shared = self.shared
            eng.reset(seed)

    def set_faults(self, faults: str | dict) -> None:
        for eng in self.engines.values():
            eng.set_faults(faults)

    def session_reset(self, session_id: str) -> None:
        for eng in self.engines.values():
            eng.session_reset(session_id)

    @property
    def sessions(self):  # for ControlAPI.health()
        return next(iter(self.engines.values())).sessions


def load_world(source: str) -> WorldDef:
    path = Path(source.split(":", 1)[1] if source.startswith("world:") else source)
    if not path.exists():
        raise FileNotFoundError(f"world file not found: {path}")
    with open(path) as f:
        return WorldDef.model_validate(yaml.safe_load(f))
