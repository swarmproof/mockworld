"""Deterministic base dataset for mock:payments (REQ-STATE-2).

Pure function of the seed: same seed → identical customers and charges, so a
fixed customer id resolves to the same balance on every run (the anchor for the
hero E2E and for reproducible declines).
"""

from __future__ import annotations

_STATUSES = ["succeeded", "succeeded", "succeeded", "requires_capture", "refunded"]


def generate(ctx, definition) -> dict:
    volume = definition.seed.volume
    customers: dict[str, dict] = {}
    charges: dict[str, dict] = {}

    for _ in range(volume.get("customers", 0)):
        cid = ctx.ids.next("cus")
        name = ctx.fake.name()
        customers[cid] = {
            "id": cid,
            "name": name,
            "email": ctx.fake.email(name),
            "balance": ctx.fake.amount_cents(50_00, 5000_00),
            "currency": "usd",
        }

    customer_ids = list(customers)
    base_ts = 1_700_000_000
    for i in range(volume.get("charges", 0)):
        chid = ctx.ids.next("ch")
        cid = ctx.rng.choice(customer_ids) if customer_ids else None
        amount = ctx.fake.amount_cents(1_00, 500_00)
        status = ctx.rng.choice(_STATUSES)
        captured = amount if status in ("succeeded", "refunded") else 0
        refunded = amount if status == "refunded" else 0
        charges[chid] = {
            "id": chid,
            "customer_id": cid,
            "amount": amount,
            "currency": "usd",
            "status": status,
            "captured": captured,
            "refunded": refunded,
            "disputed": False,
            "idempotency_key": None,
            "created": base_ts + i,
        }

    return {"customers": customers, "charges": charges}
