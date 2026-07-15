"""Deterministic base dataset for mock:crm.

Seeds a mix of record types; a fraction are `locked` (deleting them triggers
permission_denied — a stateful fault) to make the misuse demo richer.
"""

from __future__ import annotations

_TYPES = ["customer", "lead", "contact", "account", "opportunity"]


def generate(ctx, definition) -> dict:
    n = definition.seed.volume.get("records", 0)
    records: dict[str, dict] = {}

    # In a composed world, mirror the shared customers as CRM records keyed by the
    # SAME id, so get_record(customer_id) resolves across services (REQ-WORLD-1).
    for c in (ctx.shared or {}).get("customers", []):
        records[c["id"]] = {
            "id": c["id"], "type": "customer", "name": c["name"],
            "data": {"email": c["email"]}, "archived": False, "locked": False,
            "version": 1, "updated": 1_700_000_000,
        }

    for i in range(n):
        rid = ctx.ids.next("rec")
        rtype = ctx.rng.choice(_TYPES)
        name = ctx.fake.name() if rtype in ("customer", "lead", "contact") else ctx.fake.company()
        records[rid] = {
            "id": rid,
            "type": rtype,
            "name": name,
            "data": {"email": ctx.fake.email(name)},
            "archived": ctx.rng.random() < 0.1,   # ~10% already archived
            "locked": ctx.rng.random() < 0.15,     # ~15% protected from deletion
            "version": 1,
            "updated": 1_700_000_000 + i,
        }
    return {"records": records, "audit_log": {}}
