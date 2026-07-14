"""The authoritative ``mock.yaml`` schema (ARCHITECTURE §4; REQ-DEF-*).

pydantic v2 models validated against ``schema_version`` on load. Params accept a
shorthand (``amount: int``) or full form (``amount: {type: int, required: true,
min: 1}``); the shorthand normalizes to a required param of that type.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1"

ParamType = Literal["str", "int", "float", "bool", "list", "dict"]
FaultType = Literal[
    "error_response", "rate_limited", "latency", "partial_outage", "malformed_response"
]
Fidelity = Literal["exact", "partial", "sketch"]

_PY_TYPES: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


class ParamSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ParamType = "str"
    required: bool = False
    default: Any = None
    min: float | None = None
    max: float | None = None
    enum: list[Any] | None = None

    @property
    def py_type(self) -> type:
        return _PY_TYPES[self.type]


class FaultRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: FaultType
    error: str | None = None          # required for error_response
    probability: float | None = None  # seeded-dice trigger
    when: str | None = None           # conditional trigger over params/state
    retry_after_s: int | None = None  # rate_limited
    distribution: dict[str, float] | None = None  # latency: {p50_ms, p99_ms}
    down: bool = False                # partial_outage: force the tool down

    @model_validator(mode="after")
    def _check(self) -> "FaultRule":
        if self.type == "error_response" and not self.error:
            raise ValueError("error_response fault requires an `error` name")
        if self.probability is None and self.when is None and self.type not in (
            "latency",
            "partial_outage",
        ):
            raise ValueError(f"fault {self.type!r} needs a `probability` or `when` trigger")
        if self.probability is not None and not (0.0 <= self.probability <= 1.0):
            raise ValueError("probability must be in [0, 1]")
        return self


class ToolDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    params: dict[str, ParamSpec] = Field(default_factory=dict)
    behavior: str  # "crud:{create,read,update,delete,list}" | "python:handlers.<fn>"
    collection: str | None = None  # required for crud behaviors
    faults: list[FaultRule] = Field(default_factory=list)

    @field_validator("params", mode="before")
    @classmethod
    def _normalize_params(cls, v: Any) -> Any:
        # Accept shorthand `name: <type>` alongside the full ParamSpec mapping.
        if not isinstance(v, dict):
            return v
        out: dict[str, Any] = {}
        for name, spec in v.items():
            if isinstance(spec, str):
                out[name] = {"type": spec, "required": True}
            else:
                out[name] = spec
        return out

    @model_validator(mode="after")
    def _check_behavior(self) -> "ToolDef":
        if self.behavior.startswith("crud:"):
            op = self.behavior.split(":", 1)[1]
            if op not in ("create", "read", "update", "delete", "list"):
                raise ValueError(f"unknown crud op in behavior: {self.behavior!r}")
            if not self.collection:
                raise ValueError(f"crud behavior {self.behavior!r} requires `collection`")
        elif not self.behavior.startswith("python:"):
            raise ValueError(
                f"behavior must be 'crud:<op>' or 'python:handlers.<fn>', got {self.behavior!r}"
            )
        return self

    @property
    def is_crud(self) -> bool:
        return self.behavior.startswith("crud:")

    @property
    def crud_op(self) -> str | None:
        return self.behavior.split(":", 1)[1] if self.is_crud else None

    @property
    def handler_name(self) -> str | None:
        if self.behavior.startswith("python:"):
            # "python:handlers.create_charge" -> "create_charge"
            return self.behavior.split(":", 1)[1].split(".", 1)[-1]
        return None


class StateCollectionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    fields: dict[str, str] = Field(default_factory=dict)


class SeedDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generator: str = "builtin"  # "builtin" | "python:seed.<fn>"
    volume: dict[str, int] = Field(default_factory=dict)


class FaultProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inherit: str | None = None  # e.g. "tool_defaults"
    # tool_name -> {fault_or_error_name -> probability}
    overrides: dict[str, dict[str, float]] = Field(default_factory=dict)


class MockDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    name: str
    version: str = "0.1.0"
    description: str
    fidelity: Fidelity = "partial"
    state: dict[str, StateCollectionDef] = Field(default_factory=dict)
    seed: SeedDef = Field(default_factory=SeedDef)
    tools: list[ToolDef]
    fault_profiles: dict[str, FaultProfile] = Field(default_factory=dict)
    errors: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        if str(v) != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version {v!r}; this engine supports {SCHEMA_VERSION!r}"
            )
        return str(v)

    @model_validator(mode="after")
    def _check_refs(self) -> "MockDef":
        names = [t.name for t in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("duplicate tool names")
        for tool in self.tools:
            if tool.is_crud and tool.collection not in self.state:
                raise ValueError(
                    f"tool {tool.name!r} references undeclared collection {tool.collection!r}"
                )
        # Ensure the standard profiles exist so `--faults none|realistic` always resolve.
        self.fault_profiles.setdefault("none", FaultProfile())
        self.fault_profiles.setdefault("realistic", FaultProfile(inherit="tool_defaults"))
        return self

    def collection_names(self) -> list[str]:
        return list(self.state.keys())

    def tool(self, name: str) -> ToolDef | None:
        return next((t for t in self.tools if t.name == name), None)
