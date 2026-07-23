"""`mockworld new <name>` — scaffold a fresh, runnable mock (EPIC D3, NFR-DX-2).

Emits a complete four-file mock (declarative CRUD + one Python handler + seeded
data + a fidelity note) named after the user, so authoring a real mock starts
from something that already lints, runs, and is deterministic.
"""

from __future__ import annotations

from pathlib import Path

from .record import _snake

_MOCK_YAML = '''\
schema_version: "1"
name: {name}
version: "0.1.0"
description: >
  TODO: describe what real service this mock stands in for and what agents stress
  about it. Keep it agent-legible — tool descriptions are the interface.
fidelity: sketch

state:
  items:
    key: id
    fields: {{id: str, label: str, created: int}}

seed:
  generator: python:seed.generate
  volume: {{items: 10}}

tools:
  - name: create_item
    description: "Create an item with a label. Returns the created item."
    params:
      label: {{type: str, required: true}}
    behavior: python:handlers.create_item
    faults:
      - type: rate_limited
        probability: 0.05
        retry_after_s: 1

  - name: get_item
    description: "Retrieve an item by id."
    params:
      id: {{type: str, required: true}}
    behavior: crud:read
    collection: items

  - name: list_items
    description: "List all items."
    params: {{}}
    behavior: crud:list
    collection: items

fault_profiles:
  none: {{}}
  realistic: {{inherit: tool_defaults}}
'''

_HANDLERS = '''\
"""{name} handlers — draw entropy ONLY from ctx (clock/ids/rng), never time/random/uuid."""

from __future__ import annotations

from mockworld import Result


def create_item(ctx, params) -> Result:
    item = {{
        "id": ctx.ids.next("item"),
        "label": params["label"],
        "created": ctx.now(),
    }}
    ctx.state.items.put(item["id"], item)
    return Result.ok(item)
'''

_SEED = '''\
"""{name} seed — a base dataset that is a pure function of the seed."""

from __future__ import annotations


def generate(ctx, definition) -> dict:
    items: dict[str, dict] = {{}}
    for i in range(definition.seed.volume.get("items", 0)):
        iid = ctx.ids.next("item")
        items[iid] = {{"id": iid, "label": ctx.fake.word(), "created": 1_700_000_000 + i}}
    return {{"items": items}}
'''

_FIDELITY = '''\
# fidelity — mock:{name}

**Fidelity level:** `sketch`

## Models
- TODO: what this mock models.

## Faults
- `rate_limited` on `create_item`.

## Does NOT model
- TODO: the boundaries — what's out of scope (so nobody debates vendor-exactness).
'''


def new_mock(name: str, out_dir: str | None = None) -> Path:
    slug = _snake(name)
    out = Path(out_dir) if out_dir else Path.cwd() / slug
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} already exists and is not empty")
    out.mkdir(parents=True, exist_ok=True)

    (out / "mock.yaml").write_text(_MOCK_YAML.format(name=slug))
    (out / "handlers.py").write_text(_HANDLERS.format(name=slug))
    (out / "seed.py").write_text(_SEED.format(name=slug))
    (out / "fidelity.md").write_text(_FIDELITY.format(name=slug))
    return out
