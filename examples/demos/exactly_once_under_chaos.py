"""The joint chaos demo: exactly-once under a transport interruption + a business fault.

Tells the Swarm Proof cross-project story with mockworld alone:

  * TRANSPORT layer (stampede/Toxiproxy's job): the reply to a create_charge is
    "lost" mid-flight, so the agent must retry not knowing if it succeeded.
  * BUSINESS layer (mockworld's job): a seeded card_declined / latency.
  * EXACTLY-ONCE (the `exactly-once` sibling's concern): the idempotency key makes
    the side-effect fire once regardless.

Run:  python examples/demos/exactly_once_under_chaos.py
It asserts the invariants and prints a readable report; exits non-zero on failure.
"""

from __future__ import annotations

from mockworld import Engine

FORCE_DECLINE = {"overrides": {"create_charge": {"card_declined": 1.0}}}


def _charges_for(engine: Engine, customer_id: str) -> list[dict]:
    state = engine.store.snapshot_dict("stdio-default")
    return [c for c in state["charges"].values() if c["customer_id"] == customer_id]


def transport_interruption_is_exactly_once(seed: int = 7) -> dict:
    """A lost response → retry with the same idempotency key → one charge only."""
    e = Engine.from_source("mock:payments", seed=seed, faults="realistic")
    cust = e.call("create_customer", {"name": "Ada", "balance": 10_000}).data

    # Attempt 1: the server processes the charge, but "stampede" kills the
    # connection before the agent sees the reply. Server state is already mutated.
    first = e.call("create_charge",
                   {"customer_id": cust["id"], "amount": 2_500, "idempotency_key": "order-42"})
    # Attempt 2: the agent, not knowing attempt 1 landed, retries with the SAME key.
    retry = e.call("create_charge",
                   {"customer_id": cust["id"], "amount": 2_500, "idempotency_key": "order-42"})

    charges = _charges_for(e, cust["id"])
    balance = e.call("get_customer", {"customer_id": cust["id"]}).data["balance"]
    return {
        "scenario": "transport interruption + retry",
        "same_charge_returned": first.data["id"] == retry.data["id"],
        "charges_created": len(charges),
        "balance": balance,
        "pass": (first.data["id"] == retry.data["id"]) and len(charges) == 1 and balance == 7_500,
    }


def business_decline_creates_no_phantom_charge(seed: int = 7) -> dict:
    """A declined card must not leave a charge behind — and the decline is stable on retry."""
    e = Engine.from_source("mock:payments", seed=seed, faults=FORCE_DECLINE)
    cust = e.call("create_customer", {"name": "Bob", "balance": 10_000}).data

    a = e.call("create_charge", {"customer_id": cust["id"], "amount": 2_500, "idempotency_key": "order-99"})
    b = e.call("create_charge", {"customer_id": cust["id"], "amount": 2_500, "idempotency_key": "order-99"})

    charges = _charges_for(e, cust["id"])
    balance = e.call("get_customer", {"customer_id": cust["id"]}).data["balance"]
    return {
        "scenario": "business decline + retry",
        "both_declined": (not a.success) and (not b.success) and a.err.code == "card_declined",
        "charges_created": len(charges),
        "balance": balance,
        "pass": (not a.success) and (not b.success) and len(charges) == 0 and balance == 10_000,
    }


def run() -> dict:
    results = [transport_interruption_is_exactly_once(), business_decline_creates_no_phantom_charge()]
    return {"results": results, "all_pass": all(r["pass"] for r in results)}


def _print(report: dict) -> None:
    print("=" * 70)
    print("mockworld · exactly-once under chaos (transport × business faults)")
    print("=" * 70)
    for r in report["results"]:
        mark = "PASS" if r["pass"] else "FAIL"
        print(f"\n[{mark}] {r['scenario']}")
        for k, v in r.items():
            if k not in ("scenario", "pass"):
                print(f"       {k}: {v}")
    print("\n" + ("ALL PASS ✓" if report["all_pass"] else "FAILURES ✗"))


if __name__ == "__main__":
    import sys

    report = run()
    _print(report)
    sys.exit(0 if report["all_pass"] else 1)
