# mockworld — ARCHITECTURE

*System overview, engine components, authoritative mock schema, session isolation, stampede contract, registry, tech stack, ADRs.*
*Companion to `SPEC.md`, `docs/RESEARCH.md`, `docs/PRD.md`. Author: mockworld architect. Last updated: 2026-07-13.*

> **⊕ Beyond original spec** marks design that extends v1.0 `SPEC.md`. REQ-IDs reference `docs/PRD.md`.

---

## 1. System overview

mockworld is a single Python runtime (the **engine**) that loads **mock definitions** and exposes each as a stateful MCP server. One engine can host one mock or a composed **world**. Every layer is deterministic-by-construction: all nondeterminism sources (time, IDs, RNG, fault dice) are funneled through a single seeded `DeterministicContext`.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              mockworld engine (1 process)                      │
│                                                                                │
│   agents / stampede swarm ──MCP (stdio | streamable-HTTP)──┐                   │
│   control plane (stampede / CLI) ──HTTP + in-proc──┐       │                   │
│                                                    ▼       ▼                   │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │                        MCP Exposure Layer                              │    │
│  │  initialize · tools/list · tools/call · resources · Mcp-Session-Id     │    │
│  └───────────────┬───────────────────────────────────┬──────────────────┘    │
│                  │ per call                            │ session key           │
│                  ▼                                     ▼                       │
│  ┌───────────────────────────┐          ┌──────────────────────────────────┐  │
│  │   Fault Injector           │◀────────▶│   Session Manager                │  │
│  │  (seeded dice, profiles,   │          │  copy-on-write state overlays,   │  │
│  │   conditional/stateful)    │          │  keyed by Mcp-Session-Id         │  │
│  └───────────────┬───────────┘          └──────────────┬──────────────────┘  │
│                  ▼                                       ▼                      │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                    Behavior Dispatcher                                  │   │
│  │  declarative CRUD  |  python handler ABI  handler(ctx, params)->result  │   │
│  └───────────────┬────────────────────────────────────┬───────────────────┘  │
│                  ▼                                       ▼                      │
│  ┌───────────────────────────┐          ┌──────────────────────────────────┐  │
│  │  DeterministicContext      │          │   State Store                    │  │
│  │  clock · id-gen · rng      │          │   in-memory (default) | SQLite   │  │
│  │  (all seeded)              │          │   base + per-session overlay     │  │
│  └───────────────────────────┘          └──────────────┬──────────────────┘  │
│                  │                                       │                      │
│                  └───────────────┬───────────────────────┘                     │
│                                  ▼                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │  Trace Emitter → target-side spans in trace-format (NDJSON | OTLP)      │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                                │
│   loads ◀── Mock Definition(s): mock.yaml + handlers.py + seed  (from disk or  │
│             registry). A world.yaml composes several under a shared namespace. │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Request lifecycle (one `tools/call`)
1. MCP layer resolves the **session** from `Mcp-Session-Id` (stdio → single implicit session).
2. Session Manager provides a **copy-on-write view** of state (base ∪ session overlay).
3. Fault Injector rolls **seeded dice** (and evaluates conditional faults) — may short-circuit with a realistic error/latency/malformed response *before or after* the handler.
4. Behavior Dispatcher runs the declarative CRUD or the Python handler, passing a `ctx` bound to this session's state + DeterministicContext.
5. Mutations commit atomically to the session overlay.
6. Trace Emitter writes the target-side span.
7. Result (or fault) returns over MCP.

---

## 2. Design principles (the invariants everything else serves)

1. **Determinism is a hard contract, not a mode.** Every source of entropy is injected from the seed. There is no code path that reads wall-clock, `os.urandom`, dict-hash order, or an LLM. (RESEARCH §3.2, NG4.)
2. **Isolation rides MCP.** Session identity is MCP's `Mcp-Session-Id`, not a mockworld invention.
3. **Declarative first, code when needed.** 80% of a mock is data; the Python handler ABI is the escape hatch for the interesting 20%.
4. **Faults are first-class domain objects**, not error strings — they carry realistic shapes so agents fail the way they will in production.
5. **Consume siblings' primitives.** trace-format (stampede) is imported, never redefined.

---

## 3. Engine components (detailed)

| Component | Responsibility | Key types | Notes |
|-----------|----------------|-----------|-------|
| **MCP Exposure Layer** | Speak MCP over stdio + Streamable HTTP; map mock tools → MCP tools; manage session lifecycle | `MockServer`, `SessionMiddleware` | Built on FastMCP / official SDK (ADR-1) |
| **Session Manager** | Create/isolate/GC sessions; copy-on-write overlays | `Session`, `StateView` | Keyed on `Mcp-Session-Id` (§6) |
| **State Store** | Persist declared state; base dataset + overlays | `StateStore` (impl: `MemoryStore`, `SQLiteStore`) | In-memory default (ADR-3) |
| **DeterministicContext** | Seeded clock, id-gen, RNG; the single entropy source | `Clock`, `IdGen`, `Rng` | Passed into every handler via `ctx` (§5.2) |
| **Behavior Dispatcher** | Route a tool call to declarative CRUD or a Python handler | `Handler` ABI | The authoring contract (§4.3) |
| **Fault Injector** | Seeded/conditional fault decisions; profiles | `FaultRule`, `FaultProfile`, `FaultDice` | Business-logic layer only (§5.3) |
| **Trace Emitter** | Emit target-side spans in trace-format | `Span` (trace-format) | Nests under caller trace (§7.3) |
| **Control Plane** | Out-of-band reset/seed/fault/snapshot | `ControlAPI` (HTTP + in-proc) | Drives stampede integration (§7) |
| **Registry Client** | Resolve/install/verify mocks | `RegistryClient` | v0.2 (§8) |
| **Recorder** | Scaffold mocks from real traffic/OpenAPI | `Recorder` | v0.2 (§9) |

---

## 4. The authoritative mock-definition schema

A mock is a **directory**:
```
mock:payments/
  mock.yaml          # declarative definition (authoritative)
  handlers.py        # optional Python for complex behavior
  seed.py            # optional custom seeded data generation
  fidelity.md        # ⊕ what this mock does / does not model
```

### 4.1 `mock.yaml` (worked example — the marquee `mock:payments`)

```yaml
schema_version: "1"                 # engine validates against this (REQ-DEF-5)
name: payments
version: "0.1.0"
description: >
  Fake Stripe. Create/capture/refund charges and manage customers with
  realistic balances, idempotency, and errors. Amounts are in cents.
fidelity: partial                    # exact | partial | sketch  (REQ-DEF-7)

# ---- STATE: declared shape; seeded at boot (REQ-STATE-2, REQ-DET-1) ----
state:
  customers:                         # collection: keyed store
    key: id
    fields: {id: str, name: str, balance: int, currency: str}
  charges:
    key: id
    fields: {id: str, customer_id: str, amount: int, status: str,
             captured: int, refunded: int, idempotency_key: str}

seed:
  generator: builtin                 # or python:seed.generate
  volume: {customers: 100, charges: 500}

# ---- TOOLS: each = one MCP tool (REQ-MCP-1) ----
tools:
  - name: create_charge
    description: >
      Charge a customer's card. `amount` is in cents (e.g. 500 = $5.00).
      Returns a charge object with status 'succeeded' or an error. Pass
      `idempotency_key` to safely retry without double-charging.
    params:
      customer_id: {type: str, required: true}
      amount: {type: int, required: true, min: 1}
      currency: {type: str, default: usd}
      idempotency_key: {type: str, required: false}
    behavior: python:handlers.create_charge     # complex → handler (REQ-DEF-4)
    faults:                                       # business-logic faults (REQ-FAULT-1/2)
      - type: error_response
        error: card_declined                      # realistic Stripe-shaped error body
        probability: 0.05
      - type: error_response
        error: insufficient_funds
        when: "params.amount > state.customers[params.customer_id].balance"   # conditional (REQ-FAULT-4)
      - type: rate_limited
        probability: 0.02
        retry_after_s: 2
      - type: latency
        distribution: {p50_ms: 80, p99_ms: 1200}

  - name: refund_charge
    description: "Refund a charge (full or partial). `amount` defaults to the full captured amount."
    params:
      charge_id: {type: str, required: true}
      amount: {type: int, required: false}
    behavior: python:handlers.refund_charge       # enforces refund <= captured (invariant)

  - name: get_customer
    description: "Retrieve a customer by id, including current balance."
    params: {customer_id: {type: str, required: true}}
    behavior: crud:read                            # declarative — no Python (REQ-DEF-3)
    collection: customers

# ---- FAULT PROFILES: named bundles (REQ-FAULT-5) ----
fault_profiles:
  none: {}
  realistic: {inherit: tool_defaults}              # use per-tool declared faults
  hostile:
    overrides:
      create_charge: {card_declined: 0.30, rate_limited: 0.15}
```

### 4.2 Errors as first-class objects
Built-in error library ships realistic bodies (`card_declined` → `{type:"card_error", code:"card_declined", decline_code:"generic_decline", message:"Your card was declined."}`), so agents face production-shaped failures (REQ-FAULT-2). Mocks reference errors by name; custom errors declared in `mock.yaml`.

### 4.3 The Python handler ABI (`REQ-DEF-4`)

```python
# handlers.py — the escape hatch for stateful/complex logic
from mockworld import Handler, ctx, Result, faults

def create_charge(ctx, params) -> Result:
    cust = ctx.state.customers.get(params["customer_id"])
    if cust is None:
        return Result.error("resource_missing", f"No such customer: {params['customer_id']}")

    # idempotency: exactly-once semantics for retries (ties to sibling `exactly-once`)
    if key := params.get("idempotency_key"):
        if prior := ctx.state.charges.find(idempotency_key=key):
            return Result.ok(prior)               # replay, don't double-charge

    charge = {
        "id": ctx.ids.next("ch"),                 # deterministic id (REQ-DET-3)
        "customer_id": cust["id"],
        "amount": params["amount"],
        "status": "succeeded",
        "captured": params["amount"],
        "refunded": 0,
        "idempotency_key": params.get("idempotency_key"),
        "created": ctx.clock.now(),               # virtual clock (REQ-DET-2)
    }
    ctx.state.charges.put(charge["id"], charge)   # atomic commit to session overlay
    return Result.ok(charge)
```

**ABI guarantees given to handlers:**
- `ctx.state` — a copy-on-write view of *this session's* state (writes isolated; REQ-ISO-1/2).
- `ctx.clock` / `ctx.ids` / `ctx.rng` — the *only* legal entropy sources; all seeded (REQ-DET-1..4). Importing `time`, `random`, `uuid` in a handler is flagged by `mockworld validate` (REQ-DEF-6).
- `ctx.faults` — handlers may raise declared faults conditionally.
- Handlers must be **pure w.r.t. injected entropy** — same (state, params, ctx-seed) → same result. This is the determinism contract at the authoring boundary.

---

## 5. Determinism, state, and faults

### 5.1 State store (ADR-3)
- **`MemoryStore`** (default): dict-backed, fastest; ephemeral. Base dataset generated once from seed; sessions overlay.
- **`SQLiteStore`**: file-backed; enables persistence and snapshot save/load (REQ-SNAP-*). Same logical API.
- Both present a `StateView` with copy-on-write per session (§6).

### 5.2 The single entropy funnel (`DeterministicContext`)
All nondeterminism is injected, never ambient:
| Source | Deterministic replacement | Seeded by |
|--------|---------------------------|-----------|
| Wall clock | `ctx.clock` — logical time advanced per call/step | seed + step counter |
| Random | `ctx.rng` — seeded PRNG (numpy/`random.Random(seed)`) | seed |
| IDs / UUIDs | `ctx.ids.next(prefix)` — `prefix + base62(seed, seq)` | seed + per-prefix counter |
| Collection order | insertion-ordered; sorted on read where an order is exposed | — |
| Fault decisions | `FaultDice` drawn from a dedicated seeded stream | seed (separate substream) |

**Why separate substreams:** fault dice draw from an independent PRNG substream so that adding a tool call doesn't shift the fault sequence of unrelated calls — keeps repros stable under small changes (a lesson from flaky snapshot tests).

### 5.3 Fault Injector (business-logic layer — REQ-FAULT-6, PRD §7)
- **Rule types:** `error_response`, `rate_limited`, `latency`, `partial_outage`, `malformed_response`.
- **Triggers:** `probability` (seeded dice) and/or `when:` expression over `params`/`state` (conditional/stateful, REQ-FAULT-4).
- **Profiles:** `none` / `realistic` / `hostile` / custom (REQ-FAULT-5); runtime-togglable via control API (REQ-FAULT-7).
- **Determinism:** with a fixed seed + profile, the exact fault at each logical step is reproducible (REQ-FAULT-3).
- **Explicitly out of scope:** connection kills, socket timeouts, malformed *frames*, bandwidth — those are transport-layer and owned by stampede/Toxiproxy.

---

## 6. Per-session state isolation model (`REQ-ISO-*`) ⊕

**Problem the spec left open (RESEARCH G1):** "isolated per session" — but keyed how, isolated how?

**Design:**
- **Key:** the MCP `Mcp-Session-Id` (assigned at `initialize` under Streamable HTTP). Under stdio, one process = one implicit session. This is why we ride MCP instead of inventing session tokens (ADR-2).
- **Mechanism — copy-on-write overlay:**
  ```
  Base state (seeded once at boot, immutable)
        ▲            ▲            ▲
        │            │            │   reads fall through to base
   ┌────┴───┐   ┌────┴───┐   ┌────┴───┐
   │ overlay│   │ overlay│   │ overlay│   writes land in the session overlay only
   │  S-A   │   │  S-B   │   │  S-C   │
   └────────┘   └────────┘   └────────┘
  ```
  - Reads: overlay first, fall through to immutable base.
  - Writes: copy the touched entity into the overlay, mutate there.
  - Session A's writes are invisible to B (REQ-ISO-1); base is shared read-only, so 50+ sessions cost ~one dataset + small deltas (REQ-ISO-3).
- **Reset:** `reset(seed)` clears overlays and regenerates base (REQ-DET-5); `session.reset(id)` drops one overlay only (REQ-ISO-4).
- **Lifecycle:** overlay created on `initialize`, GC'd on session close or idle timeout; memory bounded (REQ-ISO-5).

**Consequence:** determinism + isolation compose — every session that starts from seed 42 and issues the same calls sees the same results, in parallel, with no locks on the read path.

---

## 7. The stampede ↔ mockworld integration contract ⊕

> This is the deep-integration contract (ROADMAP v0.3). Proposed to the stampede architect; §7.4 tracks confirmation.

### 7.1 Shape
stampede gets a new **`MockworldTarget`** adapter alongside `MCPTarget` / `HTTPTarget` / `EVMTarget`. It implements stampede's Target interface and additionally holds a **control-plane handle** to drive determinism.

```
              stampede.yaml
                   │  target: {type: mockworld, world: ecommerce, seed: 42, faults: hostile}
                   ▼
        ┌─────────────────────┐        boot(world, seed)         ┌────────────────────┐
        │  MockworldTarget    │ ───────────────────────────────▶ │  mockworld engine   │
        │  (in stampede)      │ ◀─── {mcp_endpoints, ctl_handle}─ │  (control plane)    │
        └──────────┬──────────┘                                  └─────────┬──────────┘
   discover()/     │  reset(seed), set_faults(), snapshot()                │
   invoke()        │  ▲ control plane (HTTP/in-proc)                       │
                   ▼  │                                                    ▼
        agents ── MCP tools/call ──────────────────────────────▶  mock services (sessions)
                   │                                                      │
                   └──────── one trace_id: agent spans ⊃ target spans ────┘
```

### 7.2 Interfaces (✅ confirmed with stampede architect 2026-07-13)
mockworld satisfies stampede's full `Target` protocol **and** exposes the control plane. The protocol has three methods beyond the naive `discover/invoke/reset` — `health()`, `isolation()`, `safety_descriptor()` — each of which mockworld answers cleanly:

```python
# stampede-side Target protocol (stampede/docs/ARCHITECTURE.md §2.1) — mockworld implements all of it
class Target(Protocol):
    async def discover(self) -> ToolSet: ...
    async def invoke(self, call, ctx) -> ToolResult: ...
    async def reset(self, seed: int | None = None) -> None: ...   # seed → state is a PURE FUNCTION of seed
    async def health(self) -> HealthStatus: ...
    def isolation(self) -> IsolationMode: ...                     # returns per_agent (see below)
    def safety_descriptor(self) -> SafetyDescriptor: ...          # returns {sandboxed: True}

# mockworld control plane (REQ-CTL-1) — the handle MockworldTarget holds
class ControlAPI(Protocol):
    def boot(self, world: str, seed: int, faults: str | dict) -> BootInfo: ...  # {mcp_endpoints, session_policy}
    def reset(self, seed: int) -> None: ...
    def set_faults(self, config: str | dict) -> None: ...          # stampede forwards target.faults here
    def snapshot(self) -> SnapshotRef: ...                          # v0.3 → reproducible bug-report fixtures
    def restore(self, ref: SnapshotRef) -> None: ...
    def session_reset(self, session_id: str) -> None: ...
```

Three things this buys the integration (per stampede architect):
- **`reset(seed)` — state is a pure function of the seed.** Confirmed: this is mockworld's core determinism contract (REQ-DET-5/6, ADR-4). It's the single thing mockworld gives stampede that a real target can't — it makes `stampede --dry-run` and run-diffing bit-reproducible.
- **`isolation() → per_agent`.** mockworld's per-session state isolation (§6) reports `per_agent`, giving each stampede agent its own session/tenant. This directly answers stampede's FR-TA-06 (agents confounding each other's target state) and makes the misuse-map numbers per-agent-attributable.
- **`safety_descriptor() → {sandboxed: True}`.** mockworld is inherently a sandbox, so stampede's Safety Gate auto-allows it with no operator ack — this is *why* the mockworld-backed demo is the frictionless one-command story (vs. a prod HTTP target that requires acknowledgement).

### 7.3 Trace nesting — trace-format is an OpenTelemetry GenAI **profile** (✅ confirmed)
**Correction to an earlier assumption:** trace-format is *not* a bespoke schema — it is a **profile of the OpenTelemetry GenAI semantic conventions** (stampede ADR-1). A mockworld span **is** an OTel span, so it drops into any OTel backend (Datadog/Honeycomb/New Relic) for free. mockworld therefore emits **standard `gen_ai.*` attributes + the shared `swarmproof.*` extension** — *not* a `mockworld.*` namespace.

**mockworld's target-side span** (one per `tools/call`, REQ-OBS-1/2):
- `span.kind = SERVER`, **parented to stampede's `execute_tool` CLIENT span** (same `trace_id`).
- Standard attrs populated: `gen_ai.operation.name = "execute_tool"`, `gen_ai.tool.name`, `gen_ai.tool.type`, and **`gen_ai.tool.call.id`** — the **join key**: mockworld *echoes* the exact value stampede sent.
- mockworld does **not** set `gen_ai.usage.*` (tokens are agent-side / stampede's concern).
- `swarmproof.span.side = "target"` (stampede sets `"agent"` on its CLIENT span).
- Resource: `service.name = "mockworld.<mock>"` (e.g. `mockworld.stripe`), `service.version`. Note: `swarmproof.run.id` is a **span** attribute, not a resource attribute (one collector may see many runs).
- **Fault attributes (mockworld owns this sub-namespace, ✅ shape confirmed):**
  `swarmproof.fault.type` (e.g. `"card_declined"`), `swarmproof.fault.injected` (bool), `swarmproof.fault.source` (`"mockworld"`). stampede renders these in the report's "target-native faults" section.

**Trace-context propagation (mockworld implements the consumer side):**
- **HTTP/SSE transport:** read standard **W3C `traceparent` / `tracestate` HTTP headers**; set as the parent of the handler span.
- **stdio (MCP):** read `traceparent` from the MCP request's **`_meta.traceparent`** (stdio has no headers).
- **Graceful degradation:** if propagation is absent, mockworld still emits standalone target spans — but since mockworld is ours, it always honors propagation so demos show the full client→server→state nesting (fuel for stampede's "why did you call X?" inspector).

### 7.4 Division of responsibility (the clean seam)
| Concern | stampede | mockworld |
|---------|:--------:|:---------:|
| Generate agents / behavior | ✓ | — |
| The services being acted on | — | ✓ |
| Transport/infra chaos (kill, timeout, malformed frame) | ✓ | — |
| Business-logic faults (decline, insufficient_funds, 429) | — | ✓ |
| Determinism seed for a run | drives via control plane | owns state/faults |
| trace-format schema | **authors** (OTel GenAI profile) | **consumes / produces target-side spans** |
| The Agent Readiness Report | ✓ | feeds it (misuse map uses mockworld tool descriptions) |

**Config routing:** `stampede.yaml`'s `chaos:` block drives stampede's layer; a `target.faults:` block is **forwarded** by `MockworldTarget` to mockworld's control-plane `set_faults()` — stampede does not reimplement business faults. In the report the two are rendered in separately-labeled sections ("infra faults injected by stampede" vs. "business faults injected by mockworld").

**The strongest combined demo:** stampede kills an agent mid-`create_charge` (its fault) *while* mockworld throws a `card_declined` (mockworld's fault) → does the side-effect still fire exactly once (assertion hooks into `exactly-once`)? Recovery is asserted across **both** layers at once.

**`rate_limit` deconfliction (✅ agreed):** both layers can express rate-limiting. When a `MockworldTarget` is in use, stampede **suppresses its transport-level `rate_limit`** and defers to mockworld's semantic `rate_limited` (429 + realistic `Retry-After`), gated on target type — so a 429 is never double-counted. For non-mockworld targets, stampede's transport rate_limit stands.

### 7.5 Contract status (✅ confirmed with stampede architect 2026-07-13)
All open items are resolved; RESEARCH Q1 is closed. Confirmations exchanged:
1. ✅ **Trace shape** — OTel GenAI profile; mockworld emits `span.kind=SERVER` handler spans parented to stampede's `execute_tool` CLIENT span, joined on `gen_ai.tool.call.id`; `swarmproof.span.side="target"`; fault attrs `swarmproof.fault.{type,injected,source}` (§7.3). mockworld reads `traceparent` from HTTP headers and MCP `_meta`.
2. ✅ **Target interface** — full protocol (`discover/invoke/reset(seed)/health/isolation/safety_descriptor`) implemented; `isolation()→per_agent`, `safety_descriptor()→{sandboxed:True}` (§7.2).
3. ✅ **Fault split** — transport=stampede, business=mockworld; `target.faults:` forwarded to `set_faults()`; `rate_limit` deconflicted (above).

---

## 8. Registry design (v0.2 — `REQ-REG-*`) ⊕

**Staged approach (resolves RESEARCH Q2, G6):**
- **v0.2a — index-as-repo:** a GitHub-hosted `registry.json` (awesome-list DNA) mapping `mock:<name>` → git source + version + checksum. `mockworld add mock:shopify` clones/pins. Zero infra, community-PR-driven — matches the portfolio's "registry is the moat" and awesome-list lineage.
- **v0.2b — provenance + safety:** entries carry a signature and a checksum; **handler code from the registry runs sandboxed by default** (subprocess with restricted imports/no-net; WASM/RestrictedPython evaluated — RESEARCH Q3). Locally-authored mocks stay trusted (NFR-SEC-1).
- **Versioning:** semver, pinnable (`mock:shopify@1.2.0`); state-migrations (REQ-DEF-8) keep snapshots loadable across versions.
- **Discovery:** `mockworld search <term>`; registry surfaces fidelity level + tool count + fault catalog so consumers judge quality.

---

## 9. Record-mode design (v0.2 — `REQ-REC-*`) ⊕

**Purpose:** lower the cost of authoring a new mock by scaffolding from reality.
- **Inputs:** (a) an OpenAPI/MCP tool spec → generate declarative CRUD + tool descriptions; (b) captured traffic (a proxy recording of real request/response pairs) → infer shapes, status codes, and candidate fault modes.
- **Output:** a `mock.yaml` skeleton + stubbed `handlers.py` + a synthetic seed — the author fills in stateful invariants.
- **Safety:** PII stripped/synthesized; **real secrets never persisted** (REQ-REC-2).
- **⊕ Governance:** the recording doubles as a **Pact-style contract**; `mockworld verify --against <real>` re-checks the mock's shapes vs. the live provider to detect drift (REQ-REC-3, RESEARCH §3.5) — turning fidelity drift from a weakness into a governed, testable property.

---

## 10. Tech stack & rationale

| Layer | Choice | Rationale | Alternatives rejected |
|-------|--------|-----------|-----------------------|
| Language | **Python 3.11+** | Matches agent ecosystem, stampede, MCP SDK; pattern-matching + tomllib | Node (ecosystem mismatch w/ portfolio) |
| MCP | **official `mcp` SDK + FastMCP** | Full spec, stdio + Streamable HTTP, stateful sessions via `Mcp-Session-Id`, decorator DX | Hand-rolled JSON-RPC (reinvents session mgmt) |
| HTTP / control | **FastAPI + uvicorn** | Async, aligns with stampede's stack; control API + HTTP transport | Flask (sync), bare ASGI |
| State | **in-memory default, SQLite backing** | Fast + deterministic + snapshot-able; stdlib SQLite | Postgres (infra weight for v0.1), Redis (external dep) |
| Validation | **pydantic v2** | Schema validation, handler param coercion, fast | dataclasses (no validation), jsonschema (verbose) |
| Data gen | **seeded faker** | Deterministic synthetic datasets | Faker w/o seed (nondeterministic) |
| Trace | **trace-format (from stampede)** | Portfolio primitive; OTel-compatible | Redefining our own (violates C4) |
| Packaging | **uv / hatch, single `mockworld` wheel** | Fast installs, clean deps (NFR-DEP-1) | heavy meta-packages |

---

## 11. Architecture Decision Records

### ADR-1 — Build on FastMCP / official MCP SDK (not hand-rolled JSON-RPC)
**Context:** we must speak MCP over stdio + Streamable HTTP with stateful sessions.
**Decision:** use the official `mcp` SDK / FastMCP; wrap it with our Session/Fault/Trace middleware.
**Alternatives:** hand-roll JSON-RPC (max control, but re-implements initialize/session/transport — the exact stuff generic tools get wrong per stampede §2.2A); use a non-standard framework.
**Consequences:** ✅ ride the ecosystem's session model (`Mcp-Session-Id`) and DX; ⚠️ coupled to SDK release cadence; we vendor a thin adapter to isolate churn.

### ADR-2 — Session identity = MCP `Mcp-Session-Id` (don't invent a token)
**Context:** need per-session isolation (REQ-ISO-*); RESEARCH G1.
**Decision:** key session state on MCP's `Mcp-Session-Id`; stdio = one implicit session.
**Alternatives:** custom session header/param (non-standard, agents wouldn't send it); per-process isolation (can't do 50 parallel sessions on one HTTP server — REQ-ISO-3).
**Consequences:** ✅ standards-aligned, works with any MCP client, cheap parallelism via overlays; ⚠️ depends on client sending the header (A1) — for stdio and control-driven runs we assign it ourselves.

### ADR-3 — In-memory state by default, SQLite for persistence/snapshots
**Context:** determinism + speed (NFR-PERF-*) vs. snapshots/persistence (REQ-SNAP-*).
**Decision:** `MemoryStore` default; `SQLiteStore` opt-in behind the same `StateStore` API.
**Alternatives:** always-SQLite (slower cold start, fails NFR-PERF-1); always-memory (no snapshots/persistence).
**Consequences:** ✅ ≤1s cold start + snapshot capability when needed; ⚠️ two impls to keep behaviorally identical → covered by a shared conformance test suite (TEST-PLAN).

### ADR-4 — Single seeded `DeterministicContext` as the only entropy source
**Context:** determinism is a hard contract (NG4, NFR-DET-1); RESEARCH G2.
**Decision:** funnel clock/RNG/IDs/fault-dice through one seeded context; ban ambient entropy; lint for it (REQ-DEF-6).
**Alternatives:** per-component seeding (drift, hard to reason about); best-effort determinism (fails the core promise).
**Consequences:** ✅ byte-identical replay across hosts (NFR-DET-1); ⚠️ handler authors must use `ctx.*` — enforced by validator + docs.

### ADR-5 — Declarative-first schema with a Python handler escape hatch
**Context:** low authoring friction (NFR-DX-2) + realistic stateful logic (REQ-DEF-3/4).
**Decision:** YAML declares state/tools/faults; simple CRUD needs no code; complex logic binds a handler via the ABI.
**Alternatives:** code-only (high friction, kills the registry flywheel); declarative-only (can't express refund≤captured invariants).
**Consequences:** ✅ trivial mocks in minutes, complex ones still expressible; ⚠️ two authoring modes to document.

### ADR-6 — Fault injection is business-logic-layer only; transport chaos is stampede's
**Context:** avoid overlap with stampede's Chaos Injector / Toxiproxy (RESEARCH §3.4, §6; PRD §7).
**Decision:** mockworld owns semantic faults; declines to implement transport faults.
**Alternatives:** own both (duplicates stampede, muddies the seam); own neither (misses the marquee "realistic decline").
**Consequences:** ✅ clean composition, clear positioning; ⚠️ users wanting transport chaos must layer stampede/Toxiproxy — documented explicitly.

### ADR-7 — Registry as index-repo first, package index later
**Context:** ship the moat without infra (RESEARCH Q2, §8).
**Decision:** v0.2a GitHub `registry.json`; v0.2b add signing + sandboxed handler execution.
**Alternatives:** full package index from day one (infra cost, premature); no registry (no network effect).
**Consequences:** ✅ community PRs immediately, matches awesome-list DNA; ⚠️ must add code-safety before untrusted handlers run (sequenced in v0.2b).
