"""email handlers — the stateful invariants a fake Gmail/SMTP must enforce.

  * sent persists: a successfully sent message is retrievable afterward via
    get_message / list_messages (the engine commits state only on success).
  * bounces are sticky: an address in `bounced_addresses` ALWAYS hard-bounces,
    on every retry. That collection is seeded into the immutable base, so the
    stickiness signal survives independently of any single call's outcome (the
    engine rolls back writes on an error result — REQ-STATE-3 — so a bounce
    leaves no partial row; the durable signal is the seeded address itself).
  * threading: a send with a `thread_id` joins that conversation; a send without
    one mints a fresh thread id, so replies group and new sends don't.

All entropy comes from `ctx` (clock/ids/rng); importing time/random/uuid here
would be flagged by `mockworld validate`.
"""

from __future__ import annotations

from mockworld import Result

_OWNER = "me@mockworld.local"


def send_email(ctx, params) -> Result:
    to = params["to"]

    # Sticky permanent bounce: a known-dead address always fails, on every retry.
    # (Under the `realistic`/`hostile` profiles the declared `hard_bounce` fault
    # short-circuits here too; this keeps the behavior true even under `none`.)
    if ctx.state.bounced_addresses.exists(to):
        return Result.error(
            "hard_bounce",
            f"The recipient address {to} permanently rejected the message.",
        )

    # Threading: reuse the caller's thread, else start a new conversation.
    thread_id = params.get("thread_id") or ctx.ids.next("thread")

    message = {
        "id": ctx.ids.next("msg"),
        "thread_id": thread_id,
        "to": to,
        "from": params.get("from") or _OWNER,
        "subject": params["subject"],
        "body": params["body"],
        "folder": "sent",
        "status": "sent",
        "created": ctx.now(),
    }
    ctx.state.messages.put(message["id"], message)
    return Result.ok(message)


def list_messages(ctx, params) -> Result:
    folder = params.get("folder")
    if folder is not None:
        rows = ctx.state.messages.filter(folder=folder)
    else:
        rows = ctx.state.messages.all()
    return Result.ok({"data": rows, "count": len(rows)})


def get_message(ctx, params) -> Result:
    message = ctx.state.messages.get(params["message_id"])
    if message is None:
        return Result.error("not_found", f"No such message: {params['message_id']}")
    return Result.ok(message)


def search(ctx, params) -> Result:
    q = params["query"].lower()
    rows = [
        m
        for m in ctx.state.messages.all()
        if q in (m.get("subject") or "").lower()
        or q in (m.get("body") or "").lower()
        or q in (m.get("to") or "").lower()
    ]
    return Result.ok({"data": rows, "count": len(rows)})
