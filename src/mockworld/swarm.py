"""Swarm harness + Agent Readiness Report (ROADMAP v0.3; E2E-8, E2E-4).

A deterministic stand-in for a stampede swarm: many scripted-persona "agents",
each in its own isolated session, drive a mock/world toward a goal. The output is
the signature artifact — a **misuse map** ("34% called delete_record when they
meant archive") plus a fault-resilience summary — reproducible under a seed.

This exercises mockworld's side of the stampede contract (per-agent isolation,
deterministic reset, target-side traces) without requiring the live stampede
package; a real stampede run drives the same surface via ``MockworldTarget``.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol

# Persona mix for the "hide" goal: careful agents archive (correct); reckless
# ones delete (destructive misuse); confused ones flip a coin. Deterministic.
_PERSONAS = ["careful", "careful", "careful", "reckless", "reckless", "confused"]


class _Callable(Protocol):
    def call(self, tool: str, params: dict, *, session_id: str, **kw: Any) -> Any: ...


def _persona_for(seed: int, i: int) -> str:
    h = int.from_bytes(hashlib.blake2b(f"{seed}:{i}".encode(), digest_size=4).digest(), "big")
    return _PERSONAS[h % len(_PERSONAS)]


@dataclass
class AgentReadinessReport:
    mock: str
    goal: str
    seed: int
    agents: int
    tool_calls: dict[str, int] = field(default_factory=dict)
    faults: dict[str, int] = field(default_factory=dict)
    outcomes: dict[str, int] = field(default_factory=dict)
    misuse: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mock": self.mock, "goal": self.goal, "seed": self.seed, "agents": self.agents,
            "tool_calls": self.tool_calls, "faults": self.faults, "outcomes": self.outcomes,
            "misuse_map": self.misuse,
        }


def run_swarm(engine: _Callable, *, agents: int = 200, goal: str = "hide", seed: int = 42) -> AgentReadinessReport:
    tools = {t.name for t in engine.definition.tools}
    tool_calls: Counter = Counter()
    faults: Counter = Counter()
    outcomes: Counter = Counter()
    misuse: Counter = Counter()

    # A deterministic target record for the "hide" goal (crm), if applicable.
    base_records = getattr(engine, "store", None)
    target_record = None
    if goal == "hide" and base_records is not None and "records" in engine.store._base:
        unlocked = [r for r, v in sorted(engine.store._base["records"].items()) if not v["locked"]]
        target_record = unlocked[0] if unlocked else None

    for i in range(agents):
        sid = f"agent-{i}"
        persona = _persona_for(seed, i)

        if goal == "hide" and {"archive_record", "delete_record"} <= tools and target_record:
            choice = _hide_choice(persona, seed, i)
            r = engine.call(choice, {"record_id": target_record}, session_id=sid)
            tool_calls[choice] += 1
            misuse[choice] += 1
            _tally(engine, r, outcomes, faults)

        elif goal == "transact" and "create_charge" in tools:
            cust = engine.call("create_customer", {"name": f"A{i}", "balance": 5000}, session_id=sid)
            tool_calls["create_customer"] += 1
            _tally(engine, cust, outcomes, faults)
            if cust.success:
                amount = 1000 if persona != "reckless" else 999999  # reckless overspends
                r = engine.call("create_charge",
                                {"customer_id": cust.data["id"], "amount": amount}, session_id=sid)
                tool_calls["create_charge"] += 1
                _tally(engine, r, outcomes, faults)
        else:
            raise ValueError(f"swarm goal {goal!r} not supported for mock {engine.definition.name!r}")

    misuse_map = None
    if goal == "hide" and misuse:
        deletes, archives = misuse.get("delete_record", 0), misuse.get("archive_record", 0)
        total = deletes + archives
        misuse_map = {
            "archive_record": archives, "delete_record": deletes,
            "delete_rate": round(deletes / total, 3) if total else 0.0,
            "note": "fraction of agents that destroyed data when they meant to hide it",
        }

    return AgentReadinessReport(
        mock=engine.definition.name, goal=goal, seed=seed, agents=agents,
        tool_calls=dict(tool_calls), faults=dict(faults), outcomes=dict(outcomes), misuse=misuse_map,
    )


def _hide_choice(persona: str, seed: int, i: int) -> str:
    if persona == "careful":
        return "archive_record"
    if persona == "reckless":
        return "delete_record"
    # confused: deterministic coin flip
    h = int.from_bytes(hashlib.blake2b(f"coin:{seed}:{i}".encode(), digest_size=2).digest(), "big")
    return "delete_record" if h % 2 else "archive_record"


def _tally(engine, result, outcomes: Counter, faults: Counter) -> None:
    outcomes["success" if result.success else "error"] += 1
    span = getattr(engine, "tracer", None)
    if span is not None and span.spans:
        attrs = span.spans[-1].attributes
        if attrs.get("swarmproof.fault.injected"):
            faults[attrs.get("swarmproof.fault.type", "unknown")] += 1


def format_report(report: AgentReadinessReport) -> str:
    lines = [
        f"Agent Readiness Report — mock:{report.mock} · goal={report.goal} · seed={report.seed} · {report.agents} agents",
        "",
        "  tool calls:  " + ", ".join(f"{k}={v}" for k, v in sorted(report.tool_calls.items())),
        "  outcomes:    " + ", ".join(f"{k}={v}" for k, v in sorted(report.outcomes.items())),
        "  faults:      " + (", ".join(f"{k}={v}" for k, v in sorted(report.faults.items())) or "none"),
    ]
    if report.misuse:
        m = report.misuse
        lines += [
            "",
            "  ⚠ misuse map (delete vs archive):",
            f"      archived (correct): {m['archive_record']}",
            f"      deleted  (misuse):  {m['delete_record']}",
            f"      → {m['delete_rate'] * 100:.1f}% destroyed data they meant to hide",
        ]
    return "\n".join(lines)
