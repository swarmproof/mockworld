# fidelity — mock:hello

**Fidelity level:** `sketch` — a teaching example, not a model of any real service.

## Models
- A greeting log: `say_hello(name)` records a greeting; `get_greeting`/`list_greetings` read them back.

## Faults
- `rate_limited` on `say_hello` (~5% under `realistic`, 50% under `hostile`).

## Does NOT model
- Anything real. It exists to show the anatomy of a mock — copy it with
  `mockworld new <name>` and grow it into something that models a real service.
