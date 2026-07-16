# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

**mockworld** — "a synthetic internet for agents": deterministic, LLM-free fake services (fake Stripe, Gmail, exchange, CRM, S3) exposed as MCP servers so agents can be built and tested without touching production. Part of the Swarm Proof toolkit; companion to [stampede](https://github.com/swarmproof/stampede) (stampede simulates the *agents*, mockworld simulates the *world* they act on). Apache-2.0.

**Current state: v0.1 + v0.2 implemented** (on feature branches; see git). Python 3.11+, official `mcp` SDK, pydantic v2, click, httpx; packaged with hatchling. Dev loop: `uv venv && uv pip install -e ".[dev]"`, then `python -m pytest -q` (53 tests, ~1s) and `mockworld <cmd>`.

### Module map (`src/mockworld/`)
- `determinism.py` — the seeded entropy funnel (clock/ids/rng/fault-dice). The root of all guarantees.
- `state.py` — `StateStore` (Memory/SQLite) + copy-on-write `StateView`; session isolation lives here.
- `session.py` — per-session logical counters. `schema.py` — pydantic `mock.yaml` models. `errors.py` — error library + `Result`.
- `faults.py` — fault injector (probabilistic + `when:` conditional). `dispatch.py` — CRUD + handler ABI. `handler_ctx.py` — the `ctx` handed to handlers.
- `loader.py` — load a mock dir (+ registry-installed resolution). `engine.py` — the transport-free call path (start here to trace a request).
- `trace.py` — OTel-GenAI-profile spans. `server.py` — MCP stdio+HTTP adapter. `control.py` — control plane + stampede `Target`. `cli.py` — commands. `validate.py` — the entropy linter.
- `registry.py` (v0.2) — `add`/`search`, checksum + safety gate. `world.py` (v0.2) — compose mocks with a shared identity pool. `record.py` (v0.2) — OpenAPI → scaffold.
- `snapshot.py` (v0.3) — portable `.mw.json` artifacts + migration. `swarm.py` (v0.3) — persona swarm → Agent Readiness Report (misuse map). `verify.py` (v0.3) — contract-drift vs OpenAPI.
- `mocks/<name>/` — the five built-ins (`mock.yaml` + `handlers.py` + `seed.py` + `fidelity.md`).

CLI: `run` (stdio/http, also `run world:<file>`), `list`, `inspect`, `validate`, `reset`, `demo`, `add`, `search`, `pack`, `record`. The engine is deliberately MCP-free; server/control/CLI are thin adapters (keeps determinism/isolation tests pure).

## Document map

- `SPEC.md` — the original v1.0 spec/PRD (root-level, high-level).
- `docs/PRD.md` — detailed requirements; **the source of REQ-IDs** (`REQ-DET-*`, `REQ-ISO-*`, `REQ-FAULT-*`, …) that every other doc cross-references.
- `docs/ARCHITECTURE.md` — authoritative design: engine components, the `mock.yaml` schema, handler ABI, session isolation, the stampede integration contract (§7), and ADRs 1–7.
- `docs/DELIVERY-PLAN.md` — milestones (v0.1/0.2/0.3), work breakdown (epics A–I), mock build order, definition of done, launch checklist.
- `docs/TEST-PLAN.md` — test pyramid, E2E scenarios (Given/When/Then), and the CI gates (G-DET, G-ISO, …) that define "green to merge/release".
- `docs/RESEARCH.md` — competitive landscape and open questions.

Doc conventions: `⊕ Beyond original spec` marks design that extends `SPEC.md`; keep REQ-ID cross-references intact when editing; keep the "Last updated" line current on `docs/*` edits.

## Architecture (the invariants all future code must serve)

1. **Determinism is a hard contract, not a mode** (ADR-4). All entropy — clock, RNG, IDs, fault dice — flows through one seeded `DeterministicContext`. Handlers may only use `ctx.clock` / `ctx.ids` / `ctx.rng`; importing `time`, `random`, `uuid` in a handler is a lint violation. Fault dice draw from a *separate* PRNG substream so adding a tool call doesn't shift unrelated faults. `reset(seed)` must be indistinguishable from a fresh boot at that seed. **No LLM in the response path, ever — that's the moat.**
2. **Session isolation rides MCP** (ADR-2). Sessions are keyed on MCP's `Mcp-Session-Id` (stdio = one implicit session), implemented as copy-on-write overlays over an immutable seeded base state — 50+ parallel sessions share one base dataset with no cross-talk.
3. **Declarative-first, Python escape hatch** (ADR-5). A mock is a directory: `mock.yaml` (authoritative), optional `handlers.py` (ABI: `handler(ctx, params) -> Result`, pure w.r.t. injected entropy), optional `seed.py`, and `fidelity.md` documenting what it does/doesn't model. Simple CRUD needs no code.
4. **Fault split with stampede** (ADR-6): mockworld owns *business-logic* faults only (`card_declined`, `insufficient_funds`, `rate_limited`, latency, partial outage) as first-class objects with realistic error bodies. Transport chaos (connection kills, socket timeouts, malformed frames) belongs to stampede/Toxiproxy — never implement it here. When a `MockworldTarget` is in use, stampede suppresses its transport rate_limit in favor of mockworld's semantic 429.
5. **State store**: `MemoryStore` default, `SQLiteStore` for persistence/snapshots, behind one `StateStore` API (ADR-3) — both must pass a shared conformance suite.
6. **Consume siblings' primitives, never redefine them.** Tracing uses stampede's trace-format, which is an **OpenTelemetry GenAI profile** — mockworld emits standard `gen_ai.*` attributes plus the shared `swarmproof.*` extension (`swarmproof.span.side="target"`, `swarmproof.fault.{type,injected,source}`). No `mockworld.*` namespace. Target spans are `span.kind=SERVER`, parented to stampede's `execute_tool` CLIENT span, joined on echoed `gen_ai.tool.call.id`; `traceparent` is read from HTTP headers or MCP `_meta.traceparent` on stdio.

### The stampede contract (confirmed 2026-07-13, ARCHITECTURE §7)

mockworld implements stampede's full `Target` protocol: `discover / invoke / reset(seed) / health / isolation() → per_agent / safety_descriptor() → {sandboxed: True}`, plus a control plane (`boot / reset / set_faults / snapshot / restore / session_reset`). `reset(seed)` means state is a *pure function* of the seed. Changes to this seam must stay consistent with stampede's side of the contract.

### v0.1 mock build order (stampede-demo-driven, not SPEC order)

`payments` (marquee) → `crm` (misuse-map demo) → `exchange` → `email` → `files`. Each mock must enforce its stateful invariants (e.g. refund ≤ captured, balance conservation, soft-delete ≠ hard-delete) and declare ≥3 seeded faults — see TEST-PLAN §7 for the per-mock acceptance table.

## Testing philosophy (when code lands)

Determinism/replay tests are the load-bearing acceptance gates, not an afterthought. Merge-blocking CI gates: G-DET (byte-identical transcripts across runs/hosts/both stores, DT-1..6), G-LINT (ambient-entropy lint + `mockworld validate`), G-ISO (isolation incl. 50 parallel sessions), G-UNIT (≥90% on engine core). E2E scenarios in TEST-PLAN §4 are the release gates.

## Conventions

- Conventional Commits (`feat:`, `fix:`, `docs:`, …); branches `feat/<short-name>`; atomic commits.
- Scope discipline: mocks are "realistic enough to break agents correctly," never vendor-exact clones (non-goal NG2) — resist fidelity scope creep; `fidelity.md` is where coverage boundaries live.
- Toolkit principles: provider-agnostic, honest over impressive, watchable & reproducible (seedable outputs).
