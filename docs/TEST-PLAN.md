# mockworld — TEST PLAN

*Strategy & pyramid, concrete e2e scenarios, determinism/reset testing, fault-injection tests, CI gates, acceptance criteria.*
*Companion to `PRD.md` / `ARCHITECTURE.md`. Author: mockworld architect. Last updated: 2026-07-13.*

> REQ-IDs reference `docs/PRD.md`. Scenarios are `Given/When/Then`.

---

## 1. Strategy & test pyramid

Determinism is mockworld's core promise, so the test strategy is inverted from a typical service: **the determinism/replay tests are load-bearing acceptance gates, not an afterthought.**

```
             ┌───────────────────────────────┐
             │  E2E (agent × mock)  ~10%       │  real MCP client drives a mock; the
             │  incl. stampede swarm run       │  scenarios in §4 — the "does it break
             └───────────────────────────────┘  agents correctly?" proof
          ┌──────────────────────────────────────┐
          │  Integration  ~30%                     │  MCP transport (stdio+HTTP), session
          │  session isolation, reset, faults,     │  isolation, control API, trace nesting
          │  store conformance, trace emission     │
          └──────────────────────────────────────┘
      ┌────────────────────────────────────────────────┐
      │  Unit + Property  ~60%                            │  DeterministicContext, fault dice,
      │  determinism properties, schema validation,       │  CoW overlay, CRUD, handler ABI,
      │  handler purity, id/clock/rng, error library      │  seed→state generation
      └────────────────────────────────────────────────┘
```

**Two cross-cutting suites that run at every level:**
- **Determinism conformance suite** — asserts byte-identical output for a fixed seed across runs, hosts, and both state stores.
- **`StateStore` conformance suite** — the same behavioral tests run against `MemoryStore` and `SQLiteStore` (ADR-3 divergence guard).

---

## 2. Determinism & reset testing (`REQ-DET-*`, `REQ-STATE-*`) — the marquee gate

| ID | Test | Method | Pass criteria |
|----|------|--------|---------------|
| DT-1 | **Seed → identical initial state** | Boot twice with `--seed 42`; hash full state | Hashes equal |
| DT-2 | **Seed → identical transcript** | Run a fixed script of 20 tool calls twice at seed 42; capture ordered results | Byte-identical, incl. IDs, timestamps, order |
| DT-3 | **reset ≡ restart** (REQ-DET-5) | `reset(42)` on a dirtied world vs. fresh `run(42)`; compare state | Identical |
| DT-4 | **Cross-host / cross-process** (REQ-DET-6) | Same seed on CI Linux runner + local mac; compare transcript hashes | Identical |
| DT-5 | **Store parity** | Same script vs. `MemoryStore` and `SQLiteStore` | Identical results |
| DT-6 | **Virtual clock only** (REQ-DET-2) | Static + runtime scan: no `time.*`/`datetime.now`/`uuid`/`random` in handlers | Zero violations (lint gate) |
| DT-7 | **Fault-dice stability** (§5.2) | Insert an unrelated tool call mid-script; fault sequence of other calls unchanged | Unchanged (independent substreams) |
| DT-8 | **Property: entropy funnel** | Property test — for random (state,params), same ctx-seed → same handler output | Holds ∀ generated inputs |

**Determinism is a CI gate: DT-1..DT-6 must be green to merge.** (Aligns with the advertised "100% seed-reproducible" promise, PRD §9.)

---

## 3. Session isolation testing (`REQ-ISO-*`)

| ID | Test | Method | Pass |
|----|------|--------|------|
| ISO-1 | **Write isolation** | Session A creates charge; session B `list` | B does not see A's charge |
| ISO-2 | **Shared base, isolated overlay** | Both sessions read a seeded customer; A mutates balance | B still sees seeded balance |
| ISO-3 | **50 parallel sessions** (NFR-ISO-1) | 50 concurrent HTTP sessions each run the same script at seed 42 | Each sees only its own writes; each transcript == the solo transcript |
| ISO-4 | **Independent reset** (REQ-ISO-4) | `session_reset(A)`; B untouched | A clean, B intact |
| ISO-5 | **Lifecycle GC** (REQ-ISO-5) | Open/close 1000 sessions | Memory bounded; overlays freed |

---

## 4. Concrete E2E scenarios (Given/When/Then)

> Driven by a real MCP client (and, where noted, a stampede swarm). These are the "breaks agents correctly" proofs and map to acceptance.

### E2E-1 — The hero: agent hits a seeded decline (`mock:payments`)
```
Given a mock:payments server booted with --seed 7 --faults realistic
  And a customer cus_seed7_001 with balance 50000 (cents)
When an agent calls create_charge(customer_id=cus_seed7_001, amount=2000)
  And repeats the same script in a second run at --seed 7
Then in both runs the same call at the same step returns card_declined
  And the error body is Stripe-shaped {type:"card_error", code:"card_declined", ...}
  And the agent's retry with an idempotency_key does NOT double-charge
```

### E2E-2 — Insufficient funds is stateful, not random (`mock:payments`, REQ-FAULT-4)
```
Given a customer with balance 1000
When the agent calls create_charge(amount=5000)
Then the call fails with insufficient_funds (conditional fault: amount > balance)
  And no charge is recorded and balance is unchanged
When the agent calls create_charge(amount=800)
Then it succeeds and balance becomes 200
```

### E2E-3 — Refund cannot exceed captured (`mock:payments` invariant)
```
Given a succeeded charge of 3000 (captured 3000, refunded 0)
When the agent calls refund_charge(charge_id, amount=5000)
Then the call is rejected (refund_exceeds_charge) and refunded stays 0
When the agent calls refund_charge(charge_id, amount=3000)
Then refunded becomes 3000 and a second full refund is rejected (already refunded)
```

### E2E-4 — The misuse map: delete vs archive (`mock:crm`) — stampede signature
```
Given a mock:crm world and a stampede swarm of 200 agents (mix incl. naive)
  And a goal "hide customer 4471 from the active list"
When the swarm runs
Then agents that call delete_record hard-destroy the record (irreversible)
  And agents that call archive_record soft-hide it (recoverable)
  And the CRM audit log distinguishes the two
  And stampede's Agent Readiness Report shows the % who chose delete over archive
```

### E2E-5 — Rate limit backoff (`mock:email`, REQ-FAULT-2)
```
Given mock:email with a rate_limited fault (429 + Retry-After: 2)
When an agent sends 10 emails in a tight loop
Then some calls return 429 with Retry-After at seed-deterministic steps
Then a well-behaved agent backs off; a naive agent's retry storm is visible in the trace
```

### E2E-6 — Read-after-write consistency (`mock:files`)
```
Given mock:files
When an agent put_object("report.pdf") then immediately list_objects()
Then report.pdf appears (read-after-write consistency held)
When a slow_download fault is active for get_object
Then the download returns after the injected latency, deterministically
```

### E2E-7 — Slippage surprises the agent (`mock:exchange`)
```
Given mock:exchange seeded with a market and the agent expecting price P
When the agent place_order(market, size) with a fault slippage_exceeded armed at seed
Then the fill price differs from P beyond tolerance and the order is rejected/partially filled
  And balance conservation holds (no funds created/destroyed)
```

### E2E-8 — stampede targets a mockworld world end-to-end (v0.3, REQ-STAMP-*)
```
Given stampede.yaml: target {type: mockworld, world: ecommerce, seed: 42, faults: hostile}
When stampede boots the world via the control plane and runs a 100-agent swarm
Then each agent gets an isolated session; reset(42) makes the run reproducible
  And every tool call emits a target-side span nested under the agent's trace (one trace_id)
  And re-running with the same seed yields a diffable, near-identical report
```

### E2E-9 — Scenario snapshot reproduces a bug (v0.3, REQ-SNAP-*)
```
Given a world dirtied into a failing state and saved via snapshot save bug123.mw
When a maintainer on another machine runs snapshot load bug123.mw
Then the exact world state (seed + versions + overlays) is reconstructed
  And the failing agent transcript reproduces
```

---

## 5. Fault-injection tests (`REQ-FAULT-*`)

| ID | Test | Pass |
|----|------|------|
| FLT-1 | **Probabilistic fault is seed-deterministic** | Same seed → fault at same logical steps (FAULT-3) |
| FLT-2 | **Conditional fault fires on state** | `when: amount>balance` triggers iff condition true (FAULT-4) |
| FLT-3 | **Profiles switch behavior** | `none`→0 faults; `hostile`→elevated rate per overrides (FAULT-5) |
| FLT-4 | **Runtime toggle** | `set_faults(hostile)` via control API changes behavior without restart (FAULT-7) |
| FLT-5 | **Error bodies are realistic** | Injected errors match the shared error library shapes (FAULT-2) |
| FLT-6 | **Latency distribution** | Injected latency samples match declared p50/p99 under seed |
| FLT-7 | **Malformed response** | `malformed_response` returns schema-plausible-but-wrong / truncated payload |
| FLT-8 | **Partial outage** | One tool down while siblings up; agent double-action risk observable |
| FLT-9 | **Layer boundary** (ADR-6) | mockworld never injects transport faults (kills/socket timeouts) — those are stampede's |

---

## 6. Contract / integration & observability tests

| ID | Test | REQ | Pass |
|----|------|-----|------|
| INT-1 | MCP `initialize` + `tools/list` over stdio | MCP-2 | Tools advertised with descriptions |
| INT-2 | Same over Streamable HTTP incl. `Mcp-Session-Id` | MCP-2,3 | Session assigned + honored |
| INT-3 | Control API reset/seed/faults/snapshot | CTL-1 | All operations effective + isolated from MCP surface (CTL-2) |
| INT-4 | Trace span per tool call w/ fault.applied | OBS-1 | Span present, correct attrs |
| INT-5 | Trace nesting under caller trace_id | OBS-2, STAMP-3 | target span is child of agent span |
| INT-6 | `mockworld validate` catches bad mocks | DEF-6 | Rejects entropy leaks, bad handler sig, weak descriptions |
| INT-7 | Registry add/pin/verify (v0.2) | REG-1,2,3 | Installs pinned version; checksum verified; handler sandboxed |
| INT-8 | Record-mode scaffolds from OpenAPI (v0.2) | REC-1 | Produces loadable mock.yaml skeleton |

---

## 7. Acceptance criteria per built-in mock

Each mock must pass its E2E scenario(s) plus this checklist (DoD §6.2):

| Mock | Must enforce (invariants) | Must inject (≥3 faults, seeded) | E2E |
|------|---------------------------|--------------------------------|-----|
| **payments** | balance≥0; refund≤captured; idempotency replay | card_declined, insufficient_funds, rate_limited, dispute | E2E-1,2,3 |
| **crm** | soft-delete≠hard-delete; audit log; optimistic lock | not_found, permission_denied, stale_write | E2E-4 |
| **exchange** | balance conservation; order→fill lifecycle | insufficient_funds, slippage_exceeded, market_halted | E2E-7 |
| **email** | sent persists; bounces sticky; threading | hard_bounce, rate_limited, spam_rejected | E2E-5 |
| **files** | read-after-write; versioning | not_found, access_denied, slow_download | E2E-6 |

---

## 8. CI gates (must-be-green to merge / release)

| Gate | Scope | Blocks |
|------|-------|--------|
| **G-DET** | DT-1..DT-6 (determinism + cross-host + store parity) | merge |
| **G-LINT** | DT-6 entropy lint + `mockworld validate` on all built-in mocks | merge |
| **G-ISO** | ISO-1..ISO-3 (isolation incl. 50 parallel) | merge |
| **G-UNIT** | unit + property suite ≥90% on engine core | merge |
| **G-E2E** | E2E-1..E2E-7 (all built-in mocks) | release v0.1 |
| **G-FLT** | FLT-1..FLT-9 | release |
| **G-TRACE** | INT-4,INT-5 (emission + nesting) | release |
| **G-STAMP** | E2E-8 (stampede round-trip) | release v0.3 |
| **G-PERF** | NFR-PERF-1..3 (cold start ≤1s, p95 overhead, throughput) | release |
| **G-SELFHOST** | clean-machine `pip install` + offline quickstart | release |

---

## 9. Acceptance criteria per feature tier

| Tier | Green when |
|------|-----------|
| **T0 (v0.1 core)** | G-DET, G-LINT, G-ISO, G-UNIT, G-E2E, G-FLT, G-TRACE, G-PERF, G-SELFHOST all pass; 5 mocks pass §7 |
| **T1 (stretch)** | validate linter + fidelity checklists + control API + conditional faults covered by tests |
| **T2 (v0.2)** | INT-7 (registry) + INT-8 (record) + a composed world E2E pass; ≥1 external mock added via PR |
| **T3 (v0.3)** | G-STAMP + E2E-9 (snapshot repro) + contract-verify drift test pass |

---

## 10. Non-functional test methods

- **Performance (G-PERF):** cold-start timer (≤1s in-memory); per-call overhead microbench excluding injected latency (p95 ≤5ms mem / ≤20ms SQLite); throughput soak (≥1000 calls/s/core).
- **Offline (G-SELFHOST):** run the full quickstart in a network-namespaced container with no egress and no credentials.
- **Security (v0.2):** registry handler executed with net disabled + import allowlist; attempt egress/file-escape → blocked.
- **DX:** timed "new user → first successful tool call" (target ≤2 min) and "author a CRUD mock" (≤15 min) as periodic manual UAT.
