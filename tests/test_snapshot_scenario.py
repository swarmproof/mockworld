"""Scenario snapshot gate (REQ-SNAP-*, REQ-DEF-8): E2E-9 + cross-version migration."""

from __future__ import annotations

import pytest
from mockworld import Engine
from mockworld import snapshot as snap


def test_e2e9_snapshot_reproduces_a_dirtied_world(tmp_path):
    # Dirty a world into a specific failing/edge state, then snapshot it.
    e = Engine.from_source("mock:payments", seed=7, faults="none")
    cust = e.call("create_customer", {"name": "Bug", "balance": 5000}).data
    charge = e.call("create_charge", {"customer_id": cust["id"], "amount": 1500}).data
    e.call("refund_charge", {"charge_id": charge["id"], "amount": 1500})  # fully refunded edge state

    path = str(tmp_path / "bug123.mw.json")
    snap.save(e, path, created=123)
    assert snap.read_meta(path)["seed"] == 7

    # Reconstruct on a "different machine": fresh engine, different seed.
    other = Engine.from_source("mock:payments", seed=999, faults="none")
    snap.load(other, path)
    got = other.call("get_charge", {"charge_id": charge["id"]})
    assert got.success and got.data["refunded"] == 1500
    assert other.call("get_customer", {"customer_id": cust["id"]}).data["balance"] == 5000  # refunded back


def test_snapshot_rejects_wrong_mock(tmp_path):
    e = Engine.from_source("mock:payments", seed=7, faults="none")
    path = str(tmp_path / "s.mw.json")
    snap.save(e, path)
    with pytest.raises(snap.SnapshotError, match="is for mock"):
        snap.load(Engine.from_source("mock:crm", seed=7, faults="none"), path)


def test_snapshot_migration_across_versions(tmp_path, monkeypatch):
    e = Engine.from_source("mock:payments", seed=7, faults="none")
    cust = e.call("create_customer", {"name": "Old", "balance": 5000}).data
    path = str(tmp_path / "old.mw.json")
    snap.save(e, path)

    # Simulate loading an OLD snapshot into a NEWER engine that ships a migration.
    newer = Engine.from_source("mock:payments", seed=7, faults="none")
    monkeypatch.setattr(newer.definition, "version", "0.2.0")

    def migrate_state(state, from_version, to_version):
        for c in state.get("customers", {}).values():
            c.setdefault("delinquent", False)  # a field added in 0.2.0
        return state

    monkeypatch.setattr(newer.mock.handlers, "migrate_state", migrate_state, raising=False)
    snap.load(newer, path)
    got = newer.call("get_customer", {"customer_id": cust["id"]})
    assert got.data["delinquent"] is False  # migration ran


def test_snapshot_without_migration_errors(tmp_path, monkeypatch):
    e = Engine.from_source("mock:payments", seed=7, faults="none")
    path = str(tmp_path / "s.mw.json")
    snap.save(e, path)
    newer = Engine.from_source("mock:payments", seed=7, faults="none")
    monkeypatch.setattr(newer.definition, "version", "0.2.0")
    monkeypatch.setattr(newer.mock, "handlers", None)
    with pytest.raises(snap.SnapshotError, match="migrate_state"):
        snap.load(newer, path)
