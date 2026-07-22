"""World composition gate (REQ-WORLD-*): shared identity, namespacing, determinism."""

from __future__ import annotations

from pathlib import Path

from mockworld.world import WorldEngine, load_world

WORLD = str(Path(__file__).resolve().parents[1] / "examples" / "worlds" / "ecommerce.yaml")


def _world(seed=42):
    return WorldEngine(load_world(WORLD), seed=seed, faults="none")


def test_tools_are_namespaced_by_mock():
    w = _world()
    names = {t.name for t in w.definition.tools}
    assert "payments_create_charge" in names
    assert "crm_get_record" in names
    assert "email_send_email" in names


def test_shared_identity_across_services():
    w = _world()
    cust = w.shared["customers"][0]
    pay = w.call("payments_get_customer", {"customer_id": cust["id"]})
    crm = w.call("crm_get_record", {"record_id": cust["id"]})
    assert pay.success and crm.success
    assert pay.data["name"] == crm.data["name"] == cust["name"]


def test_cross_service_flow():
    w = _world()
    cust = w.shared["customers"][0]
    assert w.call("payments_create_charge", {"customer_id": cust["id"], "amount": 2500}).success
    assert w.call("crm_update_record", {"record_id": cust["id"], "data": {"vip": True}}).success
    assert w.call("email_send_email", {"to": cust["email"], "subject": "Receipt", "body": "Thanks"}).success


def test_world_is_deterministic():
    a = [c["id"] for c in _world().shared["customers"]]
    b = [c["id"] for c in _world().shared["customers"]]
    assert a == b
    assert [c["id"] for c in _world(seed=1).shared["customers"]] != a


def test_world_reset_reseeds_identity():
    w = _world()
    cust = w.shared["customers"][0]
    w.call("payments_create_charge", {"customer_id": cust["id"], "amount": 1000})
    w.reset(42)
    # balance restored to the seeded value (charge undone by reset)
    bal = w.call("payments_get_customer", {"customer_id": cust["id"]}).data["balance"]
    assert bal == w.engines["payments"].store._base["customers"][cust["id"]]["balance"]
