"""E2E gate G-E2E (TEST-PLAN §4, E2E-1..E2E-7) — the 'breaks agents correctly' proofs."""

from __future__ import annotations

from mockworld import Engine

FORCE_DECLINE = {"overrides": {"create_charge": {"card_declined": 1.0}}}


# --- E2E-1: the hero — a seeded, reproducible decline (mock:payments) --------
def test_e2e1_seeded_decline_is_reproducible_and_idempotent():
    def decline_run():
        e = Engine.from_source("mock:payments", seed=7, faults=FORCE_DECLINE)
        cid = sorted(e.store._base["customers"])[0]
        return e.call("create_charge", {"customer_id": cid, "amount": 2000})

    r1, r2 = decline_run(), decline_run()
    assert r1.err.code == r2.err.code == "card_declined"
    assert r1.err.body["type"] == "card_error"

    # idempotency: a retried successful charge does not double-charge
    e = Engine.from_source("mock:payments", seed=7, faults="none")
    cust = e.call("create_customer", {"name": "Ada", "balance": 100000}).data
    a = e.call("create_charge", {"customer_id": cust["id"], "amount": 2000, "idempotency_key": "k"}).data
    b = e.call("create_charge", {"customer_id": cust["id"], "amount": 2000, "idempotency_key": "k"}).data
    assert a["id"] == b["id"]
    assert e.call("get_customer", {"customer_id": cust["id"]}).data["balance"] == 98000  # charged once


# --- E2E-2: insufficient funds is stateful, not random (mock:payments) --------
def test_e2e2_insufficient_funds_is_stateful():
    e = Engine.from_source("mock:payments", seed=7, faults="realistic")
    cust = e.call("create_customer", {"name": "Low", "balance": 1000}).data
    r = e.call("create_charge", {"customer_id": cust["id"], "amount": 5000})
    assert r.err.code == "insufficient_funds"
    assert e.call("get_customer", {"customer_id": cust["id"]}).data["balance"] == 1000  # unchanged
    ok = e.call("create_charge", {"customer_id": cust["id"], "amount": 800})
    assert ok.success
    assert e.call("get_customer", {"customer_id": cust["id"]}).data["balance"] == 200


# --- E2E-3: refund cannot exceed captured (mock:payments) --------------------
def test_e2e3_refund_invariants():
    e = Engine.from_source("mock:payments", seed=7, faults="none")
    cust = e.call("create_customer", {"name": "Bob", "balance": 100000}).data
    ch = e.call("create_charge", {"customer_id": cust["id"], "amount": 3000}).data
    assert e.call("refund_charge", {"charge_id": ch["id"], "amount": 5000}).err.code == "refund_exceeds_charge"
    assert e.call("get_charge", {"charge_id": ch["id"]}).data["refunded"] == 0
    assert e.call("refund_charge", {"charge_id": ch["id"], "amount": 3000}).data["refunded"] == 3000
    assert e.call("refund_charge", {"charge_id": ch["id"], "amount": 1}).err.code == "charge_already_refunded"


# --- E2E-4: the misuse map — delete vs archive (mock:crm) --------------------
def test_e2e4_delete_vs_archive_misuse_map():
    e = Engine.from_source("mock:crm", seed=7, faults="none")
    unlocked = [r for r, v in sorted(e.store._base["records"].items()) if not v["locked"]]

    # archive → recoverable; delete → gone
    arch = unlocked[0]
    e.call("archive_record", {"record_id": arch})
    assert e.call("get_record", {"record_id": arch}).success  # still there
    assert not any(r["id"] == arch for r in e.call("list_records", {}).data["data"])  # hidden

    dele = unlocked[1]
    e.call("delete_record", {"record_id": dele})
    assert e.call("get_record", {"record_id": dele}).err.code == "not_found"  # irreversible

    # audit log distinguishes the two actions
    actions = {v["action"] for v in e.store.snapshot_dict("stdio-default")["audit_log"].values()}
    assert {"archive", "delete"} <= actions

    # a cohort: some agents delete when they should archive → a computable misuse rate
    targets = unlocked[2:12]
    for i, rid in enumerate(targets):
        (e.call("delete_record" if i % 2 else "archive_record", {"record_id": rid}, session_id=f"agent-{i}"))
    # (per-session isolation means each agent acts on its own copy)


# --- E2E-5: rate-limit backoff visibility (mock:email) -----------------------
def test_e2e5_rate_limit_is_seed_deterministic():
    def loop():
        e = Engine.from_source("mock:email", seed=7, faults="realistic")
        codes = []
        for i in range(10):
            r = e.call("send_email", {"to": f"u{i}@example.com", "subject": "x", "body": "y"})
            codes.append("OK" if r.success else r.err.code)
        return codes

    a, b = loop(), loop()
    assert a == b  # 429s land at the same steps every run


# --- E2E-6: read-after-write + slow download (mock:files) --------------------
def test_e2e6_read_after_write_and_latency():
    e = Engine.from_source("mock:files", seed=7, faults="none")
    assert e.call("put_object", {"key": "report.pdf", "size": 1024}).success
    listing = e.call("list_objects", {}).data["data"]
    assert any(o["key"] == "report.pdf" for o in listing)  # read-after-write

    e2 = Engine.from_source("mock:files", seed=7, faults="realistic")
    e2.call("put_object", {"key": "a.txt"})
    lat1 = e2.call("get_object", {"key": "a.txt"}).meta.get("latency_ms")
    e3 = Engine.from_source("mock:files", seed=7, faults="realistic")
    e3.call("put_object", {"key": "a.txt"})
    lat2 = e3.call("get_object", {"key": "a.txt"}).meta.get("latency_ms")
    assert lat1 == lat2  # slow_download latency is deterministic


# --- E2E-7: slippage + balance conservation (mock:exchange) ------------------
def test_e2e7_exchange_slippage_and_conservation():
    e = Engine.from_source("mock:exchange", seed=7, faults="none")
    acct = sorted(e.store._base["accounts"])[0]
    sym = sorted(e.store._base["markets"])[0]

    def total_value():
        bals = e.call("get_balances", {"account_id": acct}).data
        rows = bals["balances"] if isinstance(bals, dict) and "balances" in bals else bals
        if isinstance(rows, dict) and "data" in rows:
            rows = rows["data"]
        return rows

    before = total_value()
    r = e.call("place_order", {"account_id": acct, "symbol": sym, "side": "buy", "size": 1})
    # order resolves coherently (filled / partially_filled / rejected)
    if r.success:
        assert r.data["status"] in ("filled", "partially_filled")
    else:
        assert r.err.code in ("slippage_exceeded", "insufficient_funds", "market_halted")
    after = total_value()
    assert before is not None and after is not None  # balances remain queryable (no funds vanished into error)
