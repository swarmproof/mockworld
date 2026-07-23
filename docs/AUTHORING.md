# Authoring a mock

A mock is a directory of four files. The fastest start is to scaffold one:

```bash
mockworld new mystripe          # creates ./mystripe/ (lints clean, runs immediately)
mockworld run ./mystripe --seed 1
```

Or read [`src/mockworld/mocks/hello/`](../src/mockworld/mocks/hello/) — the smallest complete example.

## Anatomy

```
mystripe/
  mock.yaml      # authoritative: state, tools, faults, profiles
  handlers.py    # optional: Python for stateful/complex tools
  seed.py        # optional: the seeded base dataset
  fidelity.md    # what this mock does / doesn't model
```

## `mock.yaml`

- `schema_version: "1"`, `name`, `version`, `description`, `fidelity` (`exact`|`partial`|`sketch`).
- `state`: named collections, each with a `key` field and typed `fields`.
- `seed`: `generator: builtin` (type-driven) or `python:seed.generate` (custom), plus per-collection `volume`.
- `tools`: each becomes one MCP tool.
  - `params`: `name: <type>` shorthand (required) or `name: {type, required, default, min, max, enum}`.
  - `behavior`: `crud:{create,read,update,delete,list}` (needs `collection:`) **or** `python:handlers.<fn>`.
  - `faults`: per-tool list (see below).
- `fault_profiles`: `none`, `realistic` (`inherit: tool_defaults`), and optionally `hostile` with `overrides`.

Write tool descriptions for an agent, not a param dump — legibility is the interface (`mockworld validate` warns on thin ones).

## The handler ABI

```python
from mockworld import Result

def create_charge(ctx, params) -> Result:
    cust = ctx.state.customers.get(params["customer_id"])
    if cust is None:
        return Result.error("resource_missing", f"No such customer: {params['customer_id']}")
    charge = {"id": ctx.ids.next("ch"), "amount": params["amount"], "created": ctx.now()}
    ctx.state.charges.put(charge["id"], charge)   # commits atomically iff you return ok
    return Result.ok(charge)
```

- `ctx.state.<collection>` — copy-on-write view of **this session's** state: `.get/.put/.delete/.exists/.all/.find/.filter/.count`.
- `ctx.ids.next(prefix)` — deterministic ids. `ctx.now()` — virtual-clock unix seconds. `ctx.rng` — seeded PRNG.
- **The determinism contract:** never import `time`/`random`/`uuid`/`datetime`. All entropy comes from `ctx`. `mockworld validate` fails on violations — this is what makes `--seed 42` reproducible everywhere.
- A handler that returns `Result.error(...)` (or raises) leaves state unchanged (atomic per call).

## Faults

Business-logic faults only (declines, insufficient funds, 429s, latency, partial outage, malformed) — transport chaos belongs to stampede.

```yaml
faults:
  - type: error_response
    error: card_declined            # a name from the built-in library (or your errors: block)
    probability: 0.05               # seeded dice
  - type: error_response
    error: insufficient_funds
    when: "params.amount > state.customers[params.customer_id].balance"   # stateful/conditional
  - type: rate_limited
    probability: 0.02
    retry_after_s: 2
  - type: latency
    distribution: {p50_ms: 80, p99_ms: 1200}
```

Custom error shapes go in a top-level `errors:` block (`name: {http_status, body: {...}}`).

## Validate, seed, publish

```bash
mockworld validate ./mystripe      # schema, handler signatures, entropy smells, description quality
mockworld pack ./mystripe          # prints a registry.json entry (checksum + metadata) to publish
```

Add the printed entry to a registry index and others can `mockworld add mock:mystripe`.
