"""Fault-injection gate G-FLT (TEST-PLAN §5, FLT-1..FLT-9)."""

from __future__ import annotations

from conftest import payments_engine, seeded_customer


def _charge_codes(e, n=40, amount=100):
    cid = seeded_customer(e)
    out = []
    for _ in range(n):
        r = e.call("create_charge", {"customer_id": cid, "amount": amount})
        out.append("OK" if r.success else r.err.code)
    return out


def test_flt1_probabilistic_fault_is_seed_deterministic():
    assert _charge_codes(payments_engine(seed=3, faults="hostile")) == \
           _charge_codes(payments_engine(seed=3, faults="hostile"))


def test_flt2_conditional_fault_fires_on_state():
    e = payments_engine(seed=7, faults="realistic")
    cust = e.call("create_customer", {"name": "Low", "balance": 1000}).data
    # amount > balance → insufficient_funds via the conditional (when:) fault
    r = e.call("create_charge", {"customer_id": cust["id"], "amount": 5000})
    assert r.err.code == "insufficient_funds"
    assert e.tracer.spans[-1].attributes.get("swarmproof.fault.injected") is True
    # amount <= balance → no conditional fault
    r2 = e.call("create_charge", {"customer_id": cust["id"], "amount": 500})
    assert r2.success


def test_flt3_profiles_switch_behavior():
    none_codes = _charge_codes(payments_engine(seed=3, faults="none"))
    hostile_codes = _charge_codes(payments_engine(seed=3, faults="hostile"))
    assert set(none_codes) == {"OK"}  # none profile injects nothing
    assert hostile_codes.count("card_declined") > none_codes.count("card_declined")


def test_flt4_runtime_toggle():
    e = payments_engine(seed=3, faults="none")
    assert set(_charge_codes(e)) == {"OK"}
    e.set_faults("hostile")  # control-plane toggle, no restart
    assert "card_declined" in _charge_codes(e)


def test_flt5_error_bodies_are_realistic():
    e = payments_engine(seed=3, faults="hostile")
    cid = seeded_customer(e)
    for _ in range(40):
        r = e.call("create_charge", {"customer_id": cid, "amount": 100})
        if not r.success and r.err.code == "card_declined":
            assert r.err.body["type"] == "card_error"
            assert r.err.body["decline_code"] == "generic_decline"
            assert r.err.http_status == 402
            return
    raise AssertionError("expected at least one card_declined under hostile")


def test_flt6_latency_distribution_bounded_by_p99():
    e = payments_engine(seed=5, faults="realistic")
    cid = seeded_customer(e)
    lats = []
    for _ in range(50):
        r = e.call("create_charge", {"customer_id": cid, "amount": 100})
        lats.append(r.meta.get("latency_ms", 0))
    assert all(0 <= x <= 1200 for x in lats)  # declared p99_ms
    assert len(set(lats)) > 1                  # not a constant


def test_flt7_malformed_response_truncates_payload():
    e = payments_engine(seed=5, faults="none")
    cid = seeded_customer(e)
    ch = e.call("create_charge", {"customer_id": cid, "amount": 100}).data
    # Inject a malformed_response on get_charge at runtime.
    e.set_faults({"inherit": "tool_defaults", "overrides": {"get_charge": {"malformed_response": 1.0}}})
    r = e.call("get_charge", {"charge_id": ch["id"]})
    assert r.success and r.meta.get("malformed") is True
    assert "_truncated" in r.data  # a field was dropped / marker added


def test_flt8_partial_outage_one_tool_down():
    e = payments_engine(seed=5, faults="hostile")  # get_charge forced down
    cid = seeded_customer(e)
    ch = e.call("create_charge", {"customer_id": cid, "amount": 100})
    # create_charge may or may not be faulted, but get_charge is down under hostile
    r = e.call("get_charge", {"charge_id": (ch.data or {}).get("id", "x")})
    assert r.err.code == "partial_outage"


def test_flt9_layer_boundary_only_business_faults():
    """mockworld never injects transport faults (kills/socket timeouts) — ADR-6."""
    business = {"error_response", "rate_limited", "latency", "partial_outage", "malformed_response"}
    e = payments_engine(seed=3, faults="hostile")
    cid = seeded_customer(e)
    for _ in range(50):
        e.call("create_charge", {"customer_id": cid, "amount": 100})
    for span in e.tracer.spans:
        if span.attributes.get("swarmproof.fault.injected"):
            assert span.attributes["swarmproof.fault.type"] in business
            assert span.attributes["swarmproof.fault.source"] == "mockworld"
