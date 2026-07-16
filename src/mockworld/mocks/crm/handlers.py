"""crm handlers — the delete-vs-archive misuse demo (PRD §8, E2E-4).

The load-bearing distinction: `archive_record` sets a recoverable flag and the
record SURVIVES in the store; `delete_record` removes it PERMANENTLY. Every
mutation appends to an audit log, so a stampede report can attribute which agents
chose destroy over hide. Optimistic locking (`expected_version`) surfaces
lost-update bugs.
"""

from __future__ import annotations

from mockworld import Result


def _audit(ctx, action: str, record_id: str, actor: str | None) -> None:
    entry = {
        "id": ctx.ids.next("log"),
        "action": action,
        "record_id": record_id,
        "actor": actor or "agent",
        "at": ctx.now(),
    }
    ctx.state.audit_log.put(entry["id"], entry)


def create_record(ctx, params) -> Result:
    record = {
        "id": ctx.ids.next("rec"),
        "type": params["type"],
        "name": params["name"],
        "data": params.get("data") or {},
        "archived": False,
        "locked": False,
        "version": 1,
        "updated": ctx.now(),
    }
    ctx.state.records.put(record["id"], record)
    _audit(ctx, "create", record["id"], params.get("actor"))
    return Result.ok(record)


def get_record(ctx, params) -> Result:
    record = ctx.state.records.get(params["record_id"])
    if record is None:
        return Result.error("not_found", f"No such record: {params['record_id']}")
    return Result.ok(record)


def update_record(ctx, params) -> Result:
    record = ctx.state.records.get(params["record_id"])
    if record is None:
        return Result.error("not_found", f"No such record: {params['record_id']}")

    # Optimistic lock: reject a write based on a stale read (also declared as a
    # conditional fault so it is visible/attributable in the trace).
    expected = params.get("expected_version")
    if expected is not None and expected != record["version"]:
        return Result.error("stale_write")

    if "name" in params and params["name"] is not None:
        record["name"] = params["name"]
    if "data" in params and params["data"] is not None:
        record["data"] = params["data"]
    record["version"] += 1
    record["updated"] = ctx.now()
    ctx.state.records.put(record["id"], record)
    _audit(ctx, "update", record["id"], params.get("actor"))
    return Result.ok(record)


def archive_record(ctx, params) -> Result:
    record = ctx.state.records.get(params["record_id"])
    if record is None:
        return Result.error("not_found", f"No such record: {params['record_id']}")
    record["archived"] = True
    record["updated"] = ctx.now()
    ctx.state.records.put(record["id"], record)  # preserved — recoverable
    _audit(ctx, "archive", record["id"], params.get("actor"))
    return Result.ok(record)


def restore_record(ctx, params) -> Result:
    record = ctx.state.records.get(params["record_id"])
    if record is None:
        return Result.error("not_found", f"No such record: {params['record_id']}")
    record["archived"] = False
    record["updated"] = ctx.now()
    ctx.state.records.put(record["id"], record)
    _audit(ctx, "restore", record["id"], params.get("actor"))
    return Result.ok(record)


def delete_record(ctx, params) -> Result:
    record = ctx.state.records.get(params["record_id"])
    if record is None:
        return Result.error("not_found", f"No such record: {params['record_id']}")
    ctx.state.records.delete(record["id"])  # PERMANENT — no recovery
    _audit(ctx, "delete", record["id"], params.get("actor"))
    return Result.ok({"id": record["id"], "deleted": True, "recoverable": False})


def list_records(ctx, params) -> Result:
    include_archived = params.get("include_archived", False)
    type_filter = params.get("type")
    out = []
    for record in ctx.state.records.all():
        if record["archived"] and not include_archived:
            continue
        if type_filter and record["type"] != type_filter:
            continue
        out.append(record)
    return Result.ok({"data": out, "count": len(out)})
