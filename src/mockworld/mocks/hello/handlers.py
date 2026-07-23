"""hello handlers — the handler ABI in miniature.

A handler is `def name(ctx, params) -> Result`. It may only draw entropy from
`ctx` (clock/ids/rng) — never `time`/`random`/`uuid`, which `mockworld validate`
flags. Mutations to `ctx.state` commit atomically iff the handler returns ok.
"""

from __future__ import annotations

from mockworld import Result


def say_hello(ctx, params) -> Result:
    greeting = {
        "id": ctx.ids.next("greet"),   # deterministic id
        "name": params["name"],
        "message": f"Hello, {params['name']}!",
        "created": ctx.now(),           # virtual clock, not wall-clock
    }
    ctx.state.greetings.put(greeting["id"], greeting)
    return Result.ok(greeting)
