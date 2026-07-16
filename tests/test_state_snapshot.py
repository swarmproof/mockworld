"""State-store conformance + snapshot artifact (TEST-PLAN §1 store parity; REQ-SNAP-*)."""

from __future__ import annotations

from mockworld import Engine
from mockworld.control import ControlAPI


def test_snapshot_save_load_reproduces_state(tmp_path):
    e = Engine.from_source("mock:payments", seed=7, faults="none", store="sqlite")
    cust = e.call("create_customer", {"name": "Snap", "balance": 4200}).data
    ch = e.call("create_charge", {"customer_id": cust["id"], "amount": 200}).data

    control = ControlAPI(e)
    path = str(tmp_path / "bug123.mw")
    control.snapshot(path)

    # A fresh engine restores the exact world into a session overlay.
    e2 = Engine.from_source("mock:payments", seed=999, faults="none", store="sqlite")
    ControlAPI(e2).restore(path)
    got = e2.call("get_charge", {"charge_id": ch["id"]})
    assert got.success and got.data["amount"] == 200
    assert e2.call("get_customer", {"customer_id": cust["id"]}).data["balance"] == 4000


def test_memory_and_sqlite_snapshot_dicts_match():
    def final_state(store):
        e = Engine.from_source("mock:payments", seed=7, faults="none", store=store)
        cid = sorted(e.store._base["customers"])[0]
        for i in range(10):
            e.call("create_charge", {"customer_id": cid, "amount": 100 + i}, session_id="s")
        return e.store.snapshot_dict("s")

    assert final_state("memory") == final_state("sqlite")
