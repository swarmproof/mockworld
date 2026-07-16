"""payments handlers — the stateful invariants a fake Stripe must enforce.

  * idempotency: a retried create_charge with the same key replays, never
    double-charges (ties to the sibling `exactly-once`).
  * balance ≥ 0: a capture cannot exceed the customer's balance.
  * refund ≤ captured: a refund can never exceed the remaining captured amount.

All entropy comes from `ctx` (clock/ids/rng); importing time/random/uuid here
would be flagged by `mockworld validate`.
"""

from __future__ import annotations

from mockworld import Result


def create_charge(ctx, params) -> Result:
    cust = ctx.state.customers.get(params["customer_id"])
    if cust is None:
        return Result.error("resource_missing", f"No such customer: {params['customer_id']}")

    # Idempotency: a replayed key returns the original charge (REQ; exactly-once).
    key = params.get("idempotency_key")
    if key:
        prior = ctx.state.charges.find(idempotency_key=key)
        if prior is not None:
            return Result.ok(prior)

    amount = params["amount"]
    capture = params.get("capture", True)

    if capture and amount > cust["balance"]:
        return Result.error("insufficient_funds")

    charge = {
        "id": ctx.ids.next("ch"),
        "customer_id": cust["id"],
        "amount": amount,
        "currency": params.get("currency", "usd"),
        "status": "succeeded" if capture else "requires_capture",
        "captured": amount if capture else 0,
        "refunded": 0,
        "disputed": False,
        "idempotency_key": key,
        "created": ctx.now(),
    }
    ctx.state.charges.put(charge["id"], charge)

    if capture:
        cust["balance"] -= amount
        ctx.state.customers.put(cust["id"], cust)

    return Result.ok(charge)


def capture_charge(ctx, params) -> Result:
    charge = ctx.state.charges.get(params["charge_id"])
    if charge is None:
        return Result.error("resource_missing", f"No such charge: {params['charge_id']}")
    if charge["status"] != "requires_capture":
        return Result.error("invalid_request", "Charge is not awaiting capture.")

    cust = ctx.state.customers.get(charge["customer_id"])
    if cust is None or charge["amount"] > cust["balance"]:
        return Result.error("insufficient_funds")

    charge["captured"] = charge["amount"]
    charge["status"] = "succeeded"
    ctx.state.charges.put(charge["id"], charge)
    cust["balance"] -= charge["amount"]
    ctx.state.customers.put(cust["id"], cust)
    return Result.ok(charge)


def refund_charge(ctx, params) -> Result:
    charge = ctx.state.charges.get(params["charge_id"])
    if charge is None:
        return Result.error("resource_missing", f"No such charge: {params['charge_id']}")

    refundable = charge["captured"] - charge["refunded"]
    if refundable <= 0:
        return Result.error("charge_already_refunded")

    amount = params.get("amount")
    if amount is None:
        amount = refundable
    if amount > refundable:
        return Result.error(
            "refund_exceeds_charge",
            f"Refund of {amount} exceeds remaining captured amount {refundable}.",
        )

    charge["refunded"] += amount
    if charge["refunded"] == charge["captured"]:
        charge["status"] = "refunded"
    ctx.state.charges.put(charge["id"], charge)

    cust = ctx.state.customers.get(charge["customer_id"])
    if cust is not None:
        cust["balance"] += amount  # money returns to the customer (conservation)
        ctx.state.customers.put(cust["id"], cust)

    return Result.ok(charge)


def get_charge(ctx, params) -> Result:
    charge = ctx.state.charges.get(params["charge_id"])
    if charge is None:
        return Result.error("resource_missing", f"No such charge: {params['charge_id']}")
    return Result.ok(charge)


def create_customer(ctx, params) -> Result:
    customer = {
        "id": ctx.ids.next("cus"),
        "name": params["name"],
        "email": params.get("email"),
        "balance": params.get("balance", 0),
        "currency": params.get("currency", "usd"),
    }
    ctx.state.customers.put(customer["id"], customer)
    return Result.ok(customer)
