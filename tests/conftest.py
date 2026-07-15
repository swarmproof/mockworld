"""Shared helpers for the mockworld test suite."""

from __future__ import annotations

import hashlib
import json

from mockworld import Engine


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def payments_engine(seed: int = 7, faults: str = "realistic", store: str = "memory") -> Engine:
    return Engine.from_source("mock:payments", seed=seed, faults=faults, store=store)


def seeded_customer(engine: Engine) -> str:
    """A deterministic customer id from the seeded base dataset."""
    return sorted(engine.store._base["customers"])[0]


def charge_script(engine: Engine, session_id: str, n: int = 20, amount0: int = 100) -> list:
    """Run n create_charge calls against a seeded customer; return a comparable transcript."""
    cid = seeded_customer(engine)
    out = []
    for i in range(n):
        r = engine.call("create_charge", {"customer_id": cid, "amount": amount0 + i}, session_id=session_id)
        out.append([r.success, (r.data or {}).get("id") if r.success else r.err.code,
                    (r.data or {}).get("created") if r.success else None])
    return out
