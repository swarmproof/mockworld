"""pytest integration (persona P1/P3/P7 — the test-dependency adoption channel).

Registered as a pytest plugin via the ``pytest11`` entry point, so simply having
mockworld installed gives every test suite a ``mockworld`` fixture:

    def test_agent_handles_a_decline(mockworld):
        pay = mockworld.start("mock:payments", seed=7, faults="hostile")
        cust = pay.call("create_customer", {"name": "A", "balance": 10_000}).data
        result = my_agent.charge(pay, cust["id"], 2_500)   # your agent, against a fake Stripe
        assert result.retried_sanely

Engines are in-memory and seeded, so each test is deterministic and isolated;
nothing external is touched. Use ``mockworld.world(...)`` for composed worlds.
"""

from __future__ import annotations

import pytest

from .engine import Engine


class MockworldFixture:
    """Factory handed to tests; boots deterministic engines and can reset them."""

    def __init__(self) -> None:
        self._engines: list[Engine] = []

    def start(self, source: str, *, seed: int = 0, faults: str | dict = "realistic",
              store: str = "memory") -> Engine:
        """Boot a mock (e.g. ``"mock:payments"`` or a path) as a seeded engine."""
        engine = Engine.from_source(source, seed=seed, faults=faults, store=store)
        self._engines.append(engine)
        return engine

    def world(self, source: str, *, seed: int | None = None, faults: str | dict = "realistic",
              store: str = "memory"):
        """Boot a composed world (``"world:path.yaml"``)."""
        from .world import WorldEngine, load_world

        engine = WorldEngine(load_world(source), seed=seed, faults=faults, store=store)
        return engine

    def reset_all(self, seed: int | None = None) -> None:
        for engine in self._engines:
            engine.reset(seed)


@pytest.fixture
def mockworld() -> MockworldFixture:
    """A per-test factory for deterministic, isolated mock services."""
    return MockworldFixture()
