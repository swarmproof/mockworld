# mockworld — Product Requirements Document

*Vision, goals, personas, functional & non-functional requirements, feature tiers, mock-library scope, success metrics.*
*Companion to `SPEC.md` and `docs/RESEARCH.md`. Author: mockworld architect. Last updated: 2026-07-13.*

> **⊕ Beyond original spec** marks requirements that extend the v1.0 `SPEC.md`.
> Requirement IDs are stable and referenced by `ARCHITECTURE.md`, `DELIVERY-PLAN.md`, and `TEST-PLAN.md`.

---

## 1. Vision

> **mockworld is the localhost for the agent economy** — a deterministic, LLM-free, MCP-native sandbox of high-fidelity fake services that agents can build and test against without touching production, leaking data, or spending money. Point your agent (or a stampede swarm) at a mockworld world and it can charge cards, send email, place trades, and mutate records against realistic, stateful services that reset to a known seed and inject realistic adversity — reproducibly, offline, and free.

The product is judged on one experience: **`pip install mockworld && mockworld run mock:payments` → an agent charges a fake card and hits a realistic decline, and the same seed produces the same decline every time.**

---

## 2. Goals & Non-Goals

### 2.1 Goals (v0.1)
- **G1** — A library of high-fidelity, stateful mock services, each runnable as an MCP server with **one command**.
- **G2** — **Deterministic** behavior: a seed fully determines state, IDs, timing, and fault outcomes; identical seed → identical transcript.
- **G3** — **Reset/seed** for reproducible tests; **per-session isolation** so parallel runs never collide.
- **G4** — **Fault injection**: declines, rate limits, latency, partial outages — probabilistic, seedable, and per-tool.
- **G5** — A **declarative schema** (YAML + optional Python handlers) to author new mocks, with a documented handler contract.
- **G6** — Ship the **5 built-in mocks** stampede's demos need (payments, email, exchange, crm, files), payments first.
- **G7** — Emit every interaction into the shared **trace-format** (consume stampede's schema; don't redefine).
- **G8** — First-class **DX**: fast cold start, clear errors, zero credentials, offline, provider-free.

### 2.2 Goals (v0.2 / v0.3)
- **G9** — **Registry** + `mockworld add mock:<name>` (the network-effect moat). *(v0.2)*
- **G10** — **Record-mode**: scaffold a mock from a real API's observed shapes. *(v0.2)*
- **G11** — **World composition**: a "world" = several mocks with a shared identity namespace. *(v0.2)*
- **G12** — **Deep stampede integration**: a `MockworldTarget` adapter driven from `stampede.yaml`. *(v0.3)*
- **G13** — **Scenario snapshots**: a seeded world state as a shareable, portable artifact for bug repros. *(v0.3)*

### 2.3 Non-Goals (explicit)
- **NG1** — Not a production API gateway or proxy.
- **NG2** — Not vendor-exact — fidelity is *"realistic enough to break agents correctly,"* not 100% surface coverage.
- **NG3** — Not an agent *builder* or *evaluator* (that's the agent framework / agentevals / stampede).
- **NG4** — **No LLM in the response path** — ever. (This is the moat; see RESEARCH §3.2.) LLMs may assist *authoring* offline, but never serve a tool call.
- **NG5** — Not a hosted SaaS in v0.1 (self-hosted, local-first).
- **NG6** — Not a replacement for transport-layer chaos tools (Toxiproxy/stampede own that layer; see §7 fault split).

---

## 3. Personas (from RESEARCH §5)

| ID | Persona | Primary need | v0.1 served? |
|----|---------|--------------|:------------:|
| P1 | Agent developer | Fake services to build against locally | ✓ |
| P2 | stampede user | A resettable world for a swarm | Partial (full in v0.3) |
| P3 | CI / test engineer | Determinism + isolation + parallelism | ✓ |
| P4 | Reliability / red-teamer | Realistic fault injection | ✓ |
| P5 | Educator / demo author | Offline, credential-free, safe | ✓ |
| P6 | Mock author ⊕ | Low-friction authoring + publish | Authoring ✓, publish v0.2 |
| P7 | Framework integrator ⊕ | Import as fixtures / adapter | v0.2–v0.3 |

---

## 4. Functional Requirements

Priority: **P0** = v0.1 must-ship · **P1** = v0.1 if time / early v0.2 · **P2** = v0.2+ · **P3** = v0.3+.

### 4.1 Runtime & CLI (`REQ-RT-*`)
| ID | Requirement | Priority |
|----|-------------|:--------:|
| REQ-RT-1 | `mockworld run mock:<name>` starts a mock as an MCP server over **stdio** (default) in one command. | P0 |
| REQ-RT-2 | `mockworld run mock:<name> --transport http --port <p>` serves over **Streamable HTTP** (SSE fallback). | P0 |
| REQ-RT-3 | `mockworld list` lists installed mocks with name, version, description, tool count. | P0 |
| REQ-RT-4 | `mockworld reset --seed <int>` resets a running mock's state deterministically to the seed. | P0 |
| REQ-RT-5 | `mockworld run --seed <int>` boots with a deterministic initial state. | P0 |
| REQ-RT-6 | `mockworld run <mock> --faults <profile>` selects a fault profile (`none`/`realistic`/`hostile`/custom file). | P0 |
| REQ-RT-7 | Cold start to first tool call ≤ **1s** (in-memory store). | P0 |
| REQ-RT-8 | `mockworld run world:<file>` boots a **composed world** (multiple mocks, shared namespace). | P2 |
| REQ-RT-9 | `mockworld add mock:<name>` installs a mock from the registry. | P2 |
| REQ-RT-10 | `mockworld inspect mock:<name>` prints the tool schema + fault catalog + state shape without running. | P1 |
| REQ-RT-11 | Structured, agent-legible errors (never a bare stack trace to the agent; faults return realistic API-shaped errors). | P0 |

### 4.2 MCP exposure (`REQ-MCP-*`)
| ID | Requirement | Priority |
|----|-------------|:--------:|
| REQ-MCP-1 | Each mock exposes its operations as MCP **tools** with agent-grade descriptions (legibility-tuned, not just param dumps). | P0 |
| REQ-MCP-2 | Perform MCP `initialize`; advertise tools; support `tools/list` and `tools/call`. | P0 |
| REQ-MCP-3 | Support MCP **stateful sessions** via `Mcp-Session-Id`; each session gets an isolated state overlay (see REQ-ISO-*). | P0 |
| REQ-MCP-4 | Expose read-only reference data as MCP **resources** where natural (e.g. `mock:files` object listings). | P1 |
| REQ-MCP-5 | Expose a control surface (reset/seed/fault-toggle) — as MCP tools under an admin namespace **and** as an out-of-band control API (see REQ-CTL-*). | P1 |
| REQ-MCP-6 | Tool descriptions are versioned with the mock and can be intentionally *degraded* (an "ambiguous descriptions" variant) to exercise stampede's misuse-map. ⊕ | P2 |

### 4.3 State & determinism (`REQ-STATE-*`, `REQ-DET-*`)
| ID | Requirement | Priority |
|----|-------------|:--------:|
| REQ-STATE-1 | Pluggable state store: **in-memory** (default), **SQLite** (persistable/snapshot-able). | P0 |
| REQ-STATE-2 | State is declared in the mock schema and seeded from a deterministic generator (faker-style, seed-driven). | P0 |
| REQ-STATE-3 | State mutations are atomic per tool call (no partial writes visible on fault). | P0 |
| REQ-DET-1 | A single integer **seed** fully determines: initial state, generated IDs, virtual clock, RNG, and fault dice. | P0 |
| REQ-DET-2 | A **virtual/injectable clock** — no mock reads wall-clock or `time.now()` directly; timestamps derive from seed+logical step. | P0 |
| REQ-DET-3 | Generated identifiers (charge IDs, message IDs) are deterministic functions of (seed, sequence). | P0 |
| REQ-DET-4 | Iteration/order of any collection returned to the agent is stable under a fixed seed. | P0 |
| REQ-DET-5 | `reset(seed)` returns the world to the exact state a fresh `run(seed)` would produce (reset ≡ restart). | P0 |
| REQ-DET-6 | Determinism holds across process restarts and machines (no host-dependent behavior). | P0 |

### 4.4 Session isolation (`REQ-ISO-*`)
| ID | Requirement | Priority |
|----|-------------|:--------:|
| REQ-ISO-1 | Each MCP session has a **fully isolated** view of state; writes in session A are invisible to session B. | P0 |
| REQ-ISO-2 | Sessions may share a common seeded **base** via copy-on-write; only mutations are per-session. | P0 |
| REQ-ISO-3 | N parallel CI workers (≥ 50) run against one HTTP server with zero cross-session interference. | P0 |
| REQ-ISO-4 | A session can be reset independently without affecting sibling sessions. | P1 |
| REQ-ISO-5 | Session lifecycle: created on `initialize`, GC'd on close/timeout; memory bounded. | P1 |

### 4.5 Fault injection (`REQ-FAULT-*`)
| ID | Requirement | Priority |
|----|-------------|:--------:|
| REQ-FAULT-1 | Faults are **declared per tool** in the schema, with probability and/or trigger conditions. | P0 |
| REQ-FAULT-2 | Fault taxonomy (built-in): `error_response` (business errors: `card_declined`, `insufficient_funds`, ...), `rate_limited` (429 + Retry-After), `latency` (p50/p99 distribution), `partial_outage` (per-tool up/down), `malformed_response` (schema-valid-but-wrong / truncated). | P0 |
| REQ-FAULT-3 | Fault outcomes are **deterministic under seed** (the "dice" are seeded); same seed → same faults at same steps. | P0 |
| REQ-FAULT-4 | **Conditional/stateful faults**: a fault can trigger on state (e.g. decline if `amount > 100000`), not only probabilistically. ⊕ | P1 |
| REQ-FAULT-5 | Fault **profiles**: named bundles (`none`, `realistic`, `hostile`) selectable at runtime; custom profiles via file. | P0 |
| REQ-FAULT-6 | Faults are **business-logic-layer** (application faults). Transport/infra faults are out of scope (owned by stampede/Toxiproxy). See §7. | P0 |
| REQ-FAULT-7 | Faults can be toggled at runtime via the control API without restart. | P1 |

### 4.6 Mock definition & authoring (`REQ-DEF-*`)
| ID | Requirement | Priority |
|----|-------------|:--------:|
| REQ-DEF-1 | A mock is a **directory**: `mock.yaml` (declarative) + optional `handlers.py` (Python) + `seed.py`/seed data. | P0 |
| REQ-DEF-2 | `mock.yaml` declares: `name`, `version`, `description`, `state` schema, `tools` (name, description, params, behavior, faults). | P0 |
| REQ-DEF-3 | Simple tools need **no Python** (declarative CRUD covers create/read/update/delete/list against state). | P0 |
| REQ-DEF-4 | Complex tools bind to a Python handler via a **documented ABI**: `handler(ctx, params) -> result`, where `ctx` exposes seeded state, clock, id-gen, and fault hooks. | P0 |
| REQ-DEF-5 | Schema is **versioned**; the runtime validates a mock against the schema version on load. | P0 |
| REQ-DEF-6 | `mockworld validate <mock-dir>` lints a mock (schema, handler signatures, description quality, determinism smells). ⊕ | P1 |
| REQ-DEF-7 | A mock declares its **fidelity level** and a checklist (what it does/doesn't model) — governance for the "real X does Y" debate. ⊕ | P1 |
| REQ-DEF-8 | State migrations across mock versions are declared so snapshots remain loadable. ⊕ | P2 |

### 4.7 Observability / trace (`REQ-OBS-*`)
| ID | Requirement | Priority |
|----|-------------|:--------:|
| REQ-OBS-1 | Every tool call emits a **target-side span** in the shared trace-format (tool name, params digest, result status, fault applied, latency, session id). | P0 |
| REQ-OBS-2 | Spans nest under the caller's trace via propagated `trace_id` (agent-side ⊃ target-side). | P0 |
| REQ-OBS-3 | A local **NDJSON trace sink** by default; optional OTLP export. | P1 |
| REQ-OBS-4 | `mockworld run --record-trace <file>` captures a full session trace for replay/inspection. | P1 |
| REQ-OBS-5 | Never emit secret-shaped values in traces (mocks are synthetic, but redact anyway for hygiene). | P1 |

### 4.8 Registry, record-mode, composition, snapshots (v0.2+) (`REQ-REG-*`, `REQ-REC-*`, `REQ-WORLD-*`, `REQ-SNAP-*`)
| ID | Requirement | Priority |
|----|-------------|:--------:|
| REQ-REG-1 | A registry index maps `mock:<name>` → source + version; `mockworld add` resolves and installs. | P2 |
| REQ-REG-2 | Mocks are **versioned** and pinnable (`mock:shopify@1.2.0`). | P2 |
| REQ-REG-3 | Registry entries carry provenance/signing; handler code from the registry runs sandboxed by default. ⊕ | P2 |
| REQ-REC-1 | Record-mode captures a real API's request/response shapes (from traffic or OpenAPI) to **scaffold** a mock skeleton. | P2 |
| REQ-REC-2 | Record-mode strips/synthesizes PII and never persists real secrets. ⊕ | P2 |
| REQ-REC-3 | Recorded mock can be **contract-verified** against the real provider to detect drift (Pact-style). ⊕ | P3 |
| REQ-WORLD-1 | A `world.yaml` composes multiple mocks with a **shared identity namespace** (one `customer_id` visible to payments+crm+email). | P2 |
| REQ-WORLD-2 | Composed mocks share the seed and a coherent generated dataset. | P2 |
| REQ-SNAP-1 | `mockworld snapshot save/load` serializes full world state to a portable artifact. | P3 |
| REQ-SNAP-2 | A snapshot embeds the seed, mock versions, and state; loading reproduces the exact world. | P3 |
| REQ-SNAP-3 | Snapshots are shareable in bug reports and referenced by stampede runs for repro. | P3 |

### 4.9 stampede integration (`REQ-STAMP-*`) — contract in ARCHITECTURE §7
| ID | Requirement | Priority |
|----|-------------|:--------:|
| REQ-STAMP-1 | mockworld exposes a **control-plane API** (boot/reset/seed/fault-toggle/snapshot) that stampede's `MockworldTarget` drives. | P1 (design), P3 (deep) |
| REQ-STAMP-2 | A stampede run can declare a mockworld world inline in `stampede.yaml` and get deterministic reset per run. | P3 |
| REQ-STAMP-3 | Trace nesting works end-to-end: stampede agent spans and mockworld target spans share one trace. | P1 |
| REQ-STAMP-4 | mockworld faults are drivable from `stampede.yaml` (business-logic faults declared alongside stampede's transport chaos). | P3 |

### 4.10 Control API (`REQ-CTL-*`) ⊕
| ID | Requirement | Priority |
|----|-------------|:--------:|
| REQ-CTL-1 | An out-of-band control endpoint (HTTP + in-process) exposes: `reset(seed)`, `set_faults(profile)`, `snapshot()`, `restore(snapshot)`, `session.reset(id)`. | P1 |
| REQ-CTL-2 | Control API is separable from the agent-facing MCP surface (agents can't reset their own world unless configured to). | P1 |

---

## 5. Non-Functional Requirements

| ID | Category | Requirement | Target |
|----|----------|-------------|--------|
| NFR-DET-1 | **Determinism** | Same seed → byte-identical tool outputs & fault sequence across runs/hosts. | 100% |
| NFR-ISO-1 | **Isolation** | Concurrent isolated sessions on one server. | ≥ 50 with zero cross-talk |
| NFR-PERF-1 | **Performance** | Cold start (in-memory). | ≤ 1s |
| NFR-PERF-2 | **Performance** | Tool-call overhead (excluding injected latency), p95. | ≤ 5ms in-memory / ≤ 20ms SQLite |
| NFR-PERF-3 | **Performance** | Throughput on a laptop core. | ≥ 1000 tool-calls/s |
| NFR-DX-1 | **Developer experience** | Time-to-first-successful-tool-call for a new user. | ≤ 2 min |
| NFR-DX-2 | **DX** | Authoring a trivial CRUD mock (no Python). | ≤ 15 min |
| NFR-DEP-1 | **Footprint** | Core install (no heavy deps beyond MCP SDK + FastAPI + pydantic). | `pip install mockworld` clean |
| NFR-OFFLINE-1 | **Offline** | Full functionality with no network / no credentials / no LLM. | 100% |
| NFR-SEC-1 | **Security** | Local handler code is trusted; registry handler code is sandboxed by default. | v0.2 |
| NFR-COMPAT-1 | **Compatibility** | Python 3.11+; works under stdio and Streamable HTTP MCP clients. | — |
| NFR-COST-1 | **Cost** | Zero per-call cost (no external services in the hot path). | $0 |

---

## 6. Feature set by priority tier

### Tier 0 — v0.1 core (the launch)
- One-command run (stdio + HTTP) · seed/reset determinism · per-session isolation · fault injection (taxonomy + profiles) · declarative schema + Python handler ABI · trace emission · **5 built-in mocks** · `list`/`inspect`/`validate`.

### Tier 1 — v0.1 stretch / early v0.2
- `mockworld validate` linter · fidelity checklists · control API (REQ-CTL-*) · conditional/stateful faults · degraded-description variants (misuse-map fuel) · OTLP export.

### Tier 2 — v0.2 (the moat)
- Registry + `add` + versioning/pinning + signing/sandboxing · record-mode scaffolding · world composition (shared namespace).

### Tier 3 — v0.3 (the ecosystem)
- Deep stampede integration (`MockworldTarget` + control plane + trace nesting) · scenario snapshots · contract-verify (drift governance) · framework fixtures.

---

## 7. The fault-layer split (canonical — referenced across docs)

```
LAYER                     OWNER          EXAMPLES                              FROM
────────────────────────────────────────────────────────────────────────────────
Transport / infra chaos   stampede /     connection kill, socket timeout,      stampede.yaml
                          Toxiproxy      malformed frame, bandwidth, latency   chaos: block
────────────────────────────────────────────────────────────────────────────────
Application / business    mockworld      card_declined, insufficient_funds,    mock.yaml faults:
fault injection                          rate_limited(429), partial_outage,    or control API
                                         refund_exceeds_charge, dispute
────────────────────────────────────────────────────────────────────────────────
```
mockworld owns the bottom layer only. Overlap is designed out; they compose cleanly (RESEARCH §6).

---

## 8. Built-in mock library scope (v0.1)

Prioritized by (a) stampede demo needs and (b) universality. Full tool/fault specs in `TEST-PLAN.md §7` and `DELIVERY-PLAN.md §3`.

| Order | Mock | Shape | Marquee value | Key stateful invariants | Signature faults |
|:-----:|------|-------|---------------|-------------------------|------------------|
| 1 | **mock:payments** | Stripe-shaped | The hero demo ("charge a fake card, hit a decline") | balance ≥ 0; refund ≤ captured; idempotency keys | `card_declined`, `insufficient_funds`, `rate_limited`, `dispute` |
| 2 | **mock:crm** | Records CRUD | The **delete-vs-archive misuse** demo (stampede misuse-map) | soft-delete vs hard-delete distinction; audit log | `not_found`, `permission_denied`, `stale_write` (optimistic-lock) |
| 3 | **mock:exchange** | CEX-shaped | The DeFi/finance hook | balance conservation; order→fill; slippage | `insufficient_funds`, `slippage_exceeded`, `market_halted` |
| 4 | **mock:email** | Gmail/SMTP-shaped | Universal side-effect (send/read/search) | sent persists; bounces are sticky; threading | `hard_bounce`, `rate_limited`, `spam_rejected` |
| 5 | **mock:files** | S3-shaped | Storage side-effect; read-after-write | read-after-write consistency; versioning | `not_found`, `access_denied`, `slow_download` |

**Rationale for reordering vs. spec** (spec order: payments, email, exchange, crm, files): **crm is promoted to #2** because it powers stampede's signature *misuse map* ("34% called delete_record when they meant archive") — the single most screenshot-worthy stampede artifact. payments stays #1 (the hero). email demoted to #4 (universal but least demo-differentiating). ⊕

---

## 9. Success metrics

| Metric | Target | Source |
|--------|--------|--------|
| **North star** | # mocks in community registry + # projects depending on mockworld in tests | SPEC §1.5 |
| Community mocks in 90 days | ≥ 10 | SPEC §1.5 |
| Launch stars (30 days) | driven by "fake Stripe for agents in one command" hook | SPEC §1.5 |
| Time-to-first-tool-call | ≤ 2 min | NFR-DX-1 |
| Determinism guarantee | 100% seed-reproducible (advertised as a hard promise) | NFR-DET-1 |
| stampede demos using mockworld | ≥ 2 of stampede's launch demos run on a mockworld world | ecosystem |
| Adoption depth signal ⊕ | # repos with a `mockworld` dev-dependency + a committed fault profile | new |

---

## 10. Dependencies, assumptions, constraints

**Dependencies:** official MCP Python SDK / FastMCP; FastAPI (HTTP transport + control API); pydantic (schema/validation); a seeded faker for data generation; trace-format schema (authored in **stampede** — hard dependency, see Q1 open question); SQLite (stdlib).

**Assumptions:** (A1) MCP `Mcp-Session-Id` is available and reliable for session keying under Streamable HTTP. (A2) stampede's trace-format is OTel-compatible and stable enough to target by mid-v0.1. (A3) v0.1 handler code is *locally authored and trusted* (registry sandboxing deferred to v0.2). (A4) "realistic enough to break agents correctly" is an acceptable, defensible fidelity bar.

**Constraints:** (C1) LLM-free hot path is inviolable (NG4). (C2) Apache-2.0. (C3) Must run offline on a laptop. (C4) Must not redefine trace-format or persona-pack (consume the siblings' primitives). (C5) Python 3.11+.
