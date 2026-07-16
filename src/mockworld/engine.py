"""The engine — one deterministic call path (ARCHITECTURE §1.1).

Deliberately free of any MCP dependency: the engine takes
``(session_id, tool, params)`` and returns a :class:`~mockworld.errors.Result`.
The MCP exposure layer (``server.py``) and the control plane (``control.py``) are
thin adapters over this. Keeping the core transport-free is what makes the
determinism and isolation gates fast, pure unit tests rather than MCP round-trips
(ADR-1 rationale).

Request lifecycle for one tool call:
  resolve tool → coerce params → session position → CoW view → roll fault dice →
  (short-circuit fault | run behavior) → commit-or-rollback → emit span → return.
"""

from __future__ import annotations

from typing import Any, TextIO

from .determinism import DeterministicContext
from .dispatch import BehaviorDispatcher
from .errors import Result
from .faults import FaultInjector, _malform
from .handler_ctx import FaultHelper, HandlerCtx
from .loader import LoadedMock, load_mock
from .schema import FaultProfile, ParamSpec, ToolDef
from .session import SessionManager
from .state import make_store
from .trace import TraceEmitter

STDIO_SESSION = "stdio-default"  # implicit single session under stdio (ADR-2)


class ParamError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Engine:
    def __init__(
        self,
        mock: LoadedMock,
        *,
        seed: int = 0,
        faults: str | dict = "realistic",
        store: str = "memory",
        run_id: str = "local",
        trace_sink: TextIO | None = None,
        apply_latency: bool = False,
    ) -> None:
        self.mock = mock
        self.definition = mock.definition
        self.seed = seed
        self.run_id = run_id
        self.apply_latency = apply_latency

        self.dctx = DeterministicContext(seed)
        self.store = make_store(store, self.definition.collection_names())
        self.sessions = SessionManager(self.store)
        self.injector = FaultInjector(self.dctx)
        self.dispatcher = BehaviorDispatcher(self.definition, mock.handlers)
        self.tracer = TraceEmitter(self.definition.name, self.definition.version, trace_sink)

        self._profile = self._resolve_profile(faults)
        self._seed_base()

    # -- construction helpers ----------------------------------------------------

    @classmethod
    def from_source(cls, source: str, **kwargs: Any) -> "Engine":
        return cls(load_mock(source), **kwargs)

    def _seed_base(self) -> None:
        self.store.load_base(self.mock.generate_base(self.dctx))

    def _resolve_profile(self, faults: str | dict) -> FaultProfile:
        if isinstance(faults, dict):
            return FaultProfile.model_validate(faults)
        profile = self.definition.fault_profiles.get(faults)
        if profile is None:
            raise ValueError(
                f"unknown fault profile {faults!r}; "
                f"available: {sorted(self.definition.fault_profiles)}"
            )
        return profile

    # -- control-plane operations (REQ-CTL-*, REQ-DET-5) -------------------------

    def reset(self, seed: int | None = None) -> None:
        """reset(seed) ≡ a fresh run(seed): regenerate base, drop all overlays."""
        if seed is not None:
            self.seed = seed
            self.dctx = DeterministicContext(seed)
            self.injector = FaultInjector(self.dctx)
        self.sessions.reset_all()
        self._seed_base()

    def set_faults(self, faults: str | dict) -> None:
        self._profile = self._resolve_profile(faults)

    def session_reset(self, session_id: str) -> None:
        self.sessions.reset_session(session_id)

    # -- the call path -----------------------------------------------------------

    def call(
        self,
        tool_name: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str = STDIO_SESSION,
        call_id: str | None = None,
        traceparent: str | None = None,
    ) -> Result:
        params = dict(params or {})
        tool = self.definition.tool(tool_name)
        if tool is None:
            return Result.error("unknown_tool", f"No such tool: {tool_name!r}")

        try:
            params = self._coerce_params(tool, params)
        except ParamError as exc:
            return Result.error("invalid_request", exc.message)

        session = self.sessions.get(session_id)
        idx, step = session.next_call(tool_name)

        view = self.store.view(session_id)
        ctx = HandlerCtx(
            state=view,
            clock=self.dctx.clock_for(step),
            ids=self.dctx.ids_for(tool_name, idx),
            rng=self.dctx.rng_for(tool_name, idx),
            tool=tool_name,
            faults=FaultHelper(),
        )

        outcome = self.injector.evaluate(tool, self._profile, idx, params, view)

        if outcome.pre is not None:
            result = outcome.pre  # short-circuit fault: no behavior, no state change
        else:
            try:
                result = self.dispatcher.dispatch(tool, ctx, params)
            except Exception as exc:  # never leak a stack trace to the agent (REQ-RT-11)
                view.rollback()
                result = Result.error("internal_error", f"{type(exc).__name__}: {exc}")
            else:
                if result.success:
                    view.commit()  # atomic: only a successful call mutates state
                    if outcome.malformed:
                        result.data = _malform(result.data)
                        result.meta["malformed"] = True
                else:
                    view.rollback()  # business error → no partial writes (REQ-STATE-3)

        if outcome.latency_ms:
            result.meta["latency_ms"] = outcome.latency_ms
            if self.apply_latency:
                import time  # real-time demo mode only; off during deterministic tests

                time.sleep(outcome.latency_ms / 1000)

        self._emit(tool, idx, ctx, result, outcome, call_id, traceparent)
        return result

    # -- internals ---------------------------------------------------------------

    def _emit(self, tool, idx, ctx, result, outcome, call_id, traceparent) -> None:
        span = self.tracer.build_span(
            dctx_hash=self.dctx.stable_hash("span", tool.name, idx),
            tool_name=tool.name,
            tool_type="function",
            call_id=call_id or self.dctx.ids_for(tool.name, idx).next("call"),
            clock_epoch_s=ctx.clock.now(),
            latency_ms=outcome.latency_ms,
            run_id=self.run_id,
            traceparent=traceparent,
            fault_injected=outcome.injected,
            fault_type=outcome.fault_type,
            fault_error=outcome.error_name,
            ok=result.success,
        )
        self.tracer.emit(span)

    def _coerce_params(self, tool: ToolDef, params: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, spec in tool.params.items():
            if name in params and params[name] is not None:
                out[name] = self._coerce_one(name, spec, params[name])
            elif spec.default is not None:
                out[name] = spec.default
            elif spec.required:
                raise ParamError(f"missing required parameter: {name!r}")
        # Pass through any undeclared params untouched (lenient authoring).
        for name, value in params.items():
            out.setdefault(name, value)
        return out

    @staticmethod
    def _coerce_one(name: str, spec: ParamSpec, value: Any) -> Any:
        try:
            if spec.type == "int":
                value = int(value)
            elif spec.type == "float":
                value = float(value)
            elif spec.type == "bool":
                value = bool(value)
            elif spec.type == "str":
                value = str(value)
        except (TypeError, ValueError) as exc:
            raise ParamError(f"parameter {name!r} must be {spec.type}: {exc}") from exc

        if spec.min is not None and value < spec.min:
            raise ParamError(f"parameter {name!r} must be >= {spec.min}")
        if spec.max is not None and value > spec.max:
            raise ParamError(f"parameter {name!r} must be <= {spec.max}")
        if spec.enum is not None and value not in spec.enum:
            raise ParamError(f"parameter {name!r} must be one of {spec.enum}")
        return value
