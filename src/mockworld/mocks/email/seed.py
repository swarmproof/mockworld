"""Deterministic base dataset for mock:email (REQ-STATE-2).

Pure function of the seed: same seed → identical inbox, sent items, and the set
of permanently-bounced addresses. The bounced set is fixed (not volume-driven)
so tests and demos can address a known-dead recipient and get a *demonstrably
sticky* `hard_bounce` on every attempt (the `send_email` `when:` fault and the
handler both check membership in this collection).
"""

from __future__ import annotations

# Known-dead recipients: seeded into the immutable base, so a send to any of
# these ALWAYS hard-bounces — the anchor for the "bounces are sticky" invariant.
_BOUNCED = [
    ("bounce@blackhole.test", "mailbox_unavailable_permanent"),
    ("no-such-user@example.com", "recipient_unknown"),
    ("rejected@sandbox.io", "domain_rejects_all"),
]

_FOLDERS = ["inbox", "sent"]
_OWNER = "me@mockworld.local"
_BASE_TS = 1_700_000_000


def generate(ctx, definition) -> dict:
    volume = definition.seed.volume

    bounced_addresses: dict[str, dict] = {}
    for address, reason in _BOUNCED:
        bounced_addresses[address] = {"address": address, "reason": reason}

    messages: dict[str, dict] = {}
    thread_id: str | None = None
    for i in range(volume.get("messages", 0)):
        mid = ctx.ids.next("msg")
        # Start a new thread ~half the time; otherwise continue the current one so
        # the base dataset contains real multi-message conversations.
        if thread_id is None or ctx.rng.random() < 0.5:
            thread_id = ctx.ids.next("thread")

        folder = ctx.rng.choice(_FOLDERS)
        correspondent_name = ctx.fake.name()
        correspondent = ctx.fake.email(correspondent_name)
        if folder == "sent":
            to, sender = correspondent, _OWNER
        else:
            to, sender = _OWNER, correspondent

        messages[mid] = {
            "id": mid,
            "thread_id": thread_id,
            "to": to,
            "from": sender,
            "subject": ctx.fake.sentence(3),
            "body": ctx.fake.sentence(12),
            "folder": folder,
            "status": "sent",
            "created": _BASE_TS + i,
        }

    return {"messages": messages, "bounced_addresses": bounced_addresses}
