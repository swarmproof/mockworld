"""Isolation gate G-ISO (TEST-PLAN §3, ISO-1..ISO-5)."""

from __future__ import annotations

import threading

from conftest import charge_script, payments_engine, seeded_customer


def test_iso1_write_isolation():
    e = payments_engine(seed=7, faults="none")
    cid = seeded_customer(e)
    ch = e.call("create_charge", {"customer_id": cid, "amount": 500}, session_id="A").data
    # Session B cannot see A's charge.
    assert e.call("get_charge", {"charge_id": ch["id"]}, session_id="B").success is False


def test_iso2_shared_base_isolated_overlay():
    e = payments_engine(seed=7, faults="none")
    cid = seeded_customer(e)
    base_balance = e.call("get_customer", {"customer_id": cid}, session_id="A").data["balance"]
    # A spends; B must still see the seeded balance.
    e.call("create_charge", {"customer_id": cid, "amount": 100}, session_id="A")
    assert e.call("get_customer", {"customer_id": cid}, session_id="B").data["balance"] == base_balance
    assert e.call("get_customer", {"customer_id": cid}, session_id="A").data["balance"] == base_balance - 100


def test_iso3_50_parallel_sessions_match_solo():
    """50 concurrent sessions each running the same script == the solo transcript (NFR-ISO-1)."""
    solo = charge_script(payments_engine(seed=7, faults="realistic"), "solo", n=15)

    e = payments_engine(seed=7, faults="realistic")
    results: dict[int, list] = {}
    errors: list = []

    def worker(n: int) -> None:
        try:
            results[n] = charge_script(e, f"sess-{n}", n=15)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 50
    for n, transcript in results.items():
        assert transcript == solo, f"session {n} diverged from solo"


def test_iso4_independent_session_reset():
    e = payments_engine(seed=7, faults="none")
    cid = seeded_customer(e)
    a = e.call("create_charge", {"customer_id": cid, "amount": 100}, session_id="A").data
    b = e.call("create_charge", {"customer_id": cid, "amount": 100}, session_id="B").data
    e.session_reset("A")
    # A's charge is gone; B's survives.
    assert e.call("get_charge", {"charge_id": a["id"]}, session_id="A").success is False
    assert e.call("get_charge", {"charge_id": b["id"]}, session_id="B").success is True


def test_iso5_lifecycle_gc_bounded():
    e = payments_engine(seed=7, faults="none")
    cid = seeded_customer(e)
    for i in range(200):
        sid = f"tmp-{i}"
        e.call("create_charge", {"customer_id": cid, "amount": 100}, session_id=sid)
        e.sessions.close(sid)
    assert e.sessions.count() == 0
    assert e.store.session_count() == 0
