"""The fault injector — business-logic faults only (ARCHITECTURE §5.3; REQ-FAULT-*).

mockworld owns *semantic* faults (declines, insufficient funds, 429s, latency,
partial outage, malformed bodies). Transport chaos (connection kills, socket
timeouts, malformed frames) is stampede/Toxiproxy's layer and is never injected
here (ADR-6).

Every decision is deterministic under seed: probabilistic faults draw from
``DeterministicContext.dice`` on an independent per-tool substream, and
conditional faults (``when:``) evaluate an expression over params/state. Profiles
(``none``/``realistic``/``hostile``/custom) select and amplify the rule set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .determinism import DeterministicContext
from .errors import Result, build_error
from .schema import FaultProfile, FaultRule, ToolDef
from .state import StateView


class _AttrDict(dict):
    """dict with attribute access, for ``when:`` expressions like ``params.amount``."""

    def __getattr__(self, k: str) -> Any:
        try:
            return self[k]
        except KeyError as exc:
            raise AttributeError(k) from exc


class _EvalCollection:
    def __init__(self, view: StateView, name: str) -> None:
        self._view = view
        self._name = name

    def __getitem__(self, key: str) -> _AttrDict:
        entity = self._view.collection(self._name).get(key)
        return _AttrDict(entity or {})

    def get(self, key: str) -> _AttrDict:
        return self[key]


class _EvalState:
    def __init__(self, view: StateView) -> None:
        self._view = view

    def __getattr__(self, name: str) -> _EvalCollection:
        return _EvalCollection(self._view, name)


def eval_condition(expr: str, params: dict[str, Any], view: StateView) -> bool:
    """Evaluate a ``when:`` expression in a restricted namespace.

    v0.1 trusts locally-authored mock code (PRD assumption A3); registry handler
    code is sandboxed in v0.2 (ADR-7). Builtins are stripped so the expression can
    only read ``params`` and ``state``.
    """
    namespace = {"params": _AttrDict(params), "state": _EvalState(view)}
    try:
        return bool(eval(expr, {"__builtins__": {}}, namespace))  # noqa: S307 - trusted local
    except Exception:
        # A condition that references missing state (e.g. unknown id) simply
        # doesn't fire, rather than crashing the tool call.
        return False


@dataclass
class FaultOutcome:
    """What the injector decided for one tool call."""

    pre: Result | None = None        # short-circuit result (fires instead of handler)
    latency_ms: int = 0
    malformed: bool = False
    injected: bool = False
    fault_type: str | None = None    # e.g. "error_response", "rate_limited", "latency"
    error_name: str | None = None    # e.g. "card_declined"
    meta: dict[str, Any] = field(default_factory=dict)


def _sample_latency(distribution: dict[str, float], u: float) -> int:
    """Map a uniform draw to a latency whose median is p50 and tail approaches p99."""
    p50 = float(distribution.get("p50_ms", 0))
    p99 = float(distribution.get("p99_ms", p50))
    if u < 0.5:
        return round(p50 * (u / 0.5))
    return round(p50 + (p99 - p50) * ((u - 0.5) / 0.5))


def _malform(data: Any) -> Any:
    """Return a schema-plausible-but-wrong / truncated version of a result (FLT-7)."""
    if isinstance(data, dict) and data:
        corrupted = dict(data)
        last_key = sorted(corrupted)[-1]
        del corrupted[last_key]           # truncation: a field silently missing
        corrupted["_truncated"] = True
        return corrupted
    if isinstance(data, list):
        return data[: len(data) // 2]     # half the list
    return data


class FaultInjector:
    """Resolves the effective rules for a tool under a profile and rolls the dice."""

    def __init__(self, dctx: DeterministicContext) -> None:
        self._dctx = dctx

    def resolve_rules(self, tool: ToolDef, profile: FaultProfile) -> list[FaultRule]:
        """Effective rules = tool defaults (if inherited) with profile overrides applied."""
        base: list[FaultRule] = (
            [r.model_copy(deep=True) for r in tool.faults]
            if profile.inherit == "tool_defaults"
            else []
        )
        overrides = profile.overrides.get(tool.name, {})
        for name, prob in overrides.items():
            match = next(
                (r for r in base if r.error == name or r.type == name), None
            )
            if match is not None:
                match.probability = prob
            elif name in ("rate_limited", "latency", "partial_outage", "malformed_response"):
                base.append(FaultRule(type=name, probability=prob))
            else:
                # An override naming an error → an error_response rule for it.
                base.append(FaultRule(type="error_response", error=name, probability=prob))
        return base

    def evaluate(
        self,
        tool: ToolDef,
        profile: FaultProfile,
        idx: int,
        params: dict[str, Any],
        view: StateView,
    ) -> FaultOutcome:
        outcome = FaultOutcome()
        rules = self.resolve_rules(tool, profile)

        for rule_index, rule in enumerate(rules):
            triggered = self._triggered(tool.name, idx, rule_index, rule, params, view)

            if rule.type == "latency":
                # Latency always samples (its "trigger" is the distribution itself).
                u = self._dctx.dice(tool.name, idx, rule_index)
                outcome.latency_ms = max(
                    outcome.latency_ms, _sample_latency(rule.distribution or {}, u)
                )
                continue

            if not triggered:
                continue

            if rule.type == "malformed_response":
                outcome.malformed = True
                outcome.injected = True
                outcome.fault_type = "malformed_response"
                continue

            # error_response / rate_limited / partial_outage short-circuit the handler.
            if outcome.pre is None:
                outcome.injected = True
                outcome.fault_type = rule.type
                if rule.type == "error_response":
                    outcome.error_name = rule.error
                    outcome.pre = Result.from_error(build_error(rule.error or "error"))
                elif rule.type == "rate_limited":
                    outcome.error_name = "rate_limited"
                    err = build_error("rate_limited")
                    if rule.retry_after_s is not None:
                        err.retry_after_s = rule.retry_after_s
                    outcome.pre = Result.from_error(err)
                elif rule.type == "partial_outage":
                    outcome.error_name = "partial_outage"
                    outcome.pre = Result.from_error(build_error("partial_outage"))
        return outcome

    def _triggered(
        self,
        tool_name: str,
        idx: int,
        rule_index: int,
        rule: FaultRule,
        params: dict[str, Any],
        view: StateView,
    ) -> bool:
        if rule.type == "partial_outage" and rule.down:
            return True
        if rule.when is not None and eval_condition(rule.when, params, view):
            return True
        if rule.probability is not None:
            return self._dctx.dice(tool_name, idx, rule_index) < rule.probability
        return False
