"""Swarm + Agent Readiness Report gate (E2E-8, E2E-4 at scale)."""

from __future__ import annotations

from pathlib import Path

from mockworld import Engine
from mockworld.swarm import run_swarm
from mockworld.world import WorldEngine, load_world


def test_misuse_map_is_deterministic_and_bounded():
    def report():
        return run_swarm(Engine.from_source("mock:crm", seed=42, faults="realistic"),
                         agents=200, goal="hide", seed=42)

    a, b = report(), report()
    assert a.as_dict() == b.as_dict()                      # byte-identical (run-diffable)
    m = a.misuse
    assert m["archive_record"] + m["delete_record"] == 200
    assert 0.0 < m["delete_rate"] < 1.0                    # a real, computable misuse fraction
    assert a.outcomes["success"] >= 1


def test_swarm_per_agent_isolation():
    # Each agent hides "its" target in its own session; deletes don't leak across agents.
    e = Engine.from_source("mock:crm", seed=42, faults="none")
    target = [r for r, v in sorted(e.store._base["records"].items()) if not v["locked"]][0]
    run_swarm(e, agents=50, goal="hide", seed=42)
    # The shared base record is untouched by any agent's isolated overlay.
    assert target in e.store._base["records"]


def test_transact_goal_surfaces_faults():
    report = run_swarm(Engine.from_source("mock:payments", seed=3, faults="hostile"),
                       agents=100, goal="transact", seed=3)
    assert report.tool_calls.get("create_charge", 0) > 0
    # hostile + reckless overspend → declines / insufficient_funds appear
    assert report.outcomes.get("error", 0) > 0


def test_swarm_over_a_world():
    # E2E-8: a swarm targets a composed world; the misuse map works despite
    # crm tools being namespaced (crm_archive_record / crm_delete_record).
    w = WorldEngine(load_world(str(Path(__file__).resolve().parents[1] / "examples" / "worlds" / "ecommerce.yaml")),
                    seed=42, faults="none")
    report = run_swarm(w, agents=30, goal="hide", seed=42)
    assert report.agents == 30
    assert report.misuse is not None
    assert report.misuse["archive_record"] + report.misuse["delete_record"] == 30
