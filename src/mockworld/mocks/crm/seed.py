"""Deterministic base dataset for mock:crm.

Seeds a mix of record types; a fraction are `locked` (deleting them triggers
permission_denied — a stateful fault) to make the misuse demo richer.
"""

from __future__ import annotations

_TYPES = ["customer", "lead", "contact", "account", "opportunity"]


def generate(ctx, definition) -> dict:
    n = definition.seed.volume.get("records", 0)
    records: dict[str, dict] = {}
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
