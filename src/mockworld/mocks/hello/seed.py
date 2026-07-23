"""hello seed — a base dataset that is a pure function of the seed."""

from __future__ import annotations


def generate(ctx, definition) -> dict:
    greetings: dict[str, dict] = {}
    for i in range(definition.seed.volume.get("greetings", 0)):
        gid = ctx.ids.next("greet")
        name = ctx.fake.first_name()
        greetings[gid] = {
            "id": gid,
            "name": name,
            "message": f"Hello, {name}!",
            "created": 1_700_000_000 + i,
        }
    return {"greetings": greetings}
