# mockworld — DELIVERY PLAN

*Milestones, work breakdown, mock prioritization, sequencing, effort, definition-of-done, launch checklist.*
*Companion to `PRD.md` / `ARCHITECTURE.md`. Author: mockworld architect. Last updated: 2026-07-13.*

> REQ-IDs reference `docs/PRD.md`. Effort sizing: **XS**≈½day · **S**≈1–2d · **M**≈3–5d · **L**≈1–2wk (solo, alongside Xerberus).
> Portfolio context: mockworld is Phase E (Q2), built *after* stampede v0.1 so it can be seeded with exactly the mocks stampede's demos need.

---

## 1. Milestone map

| Milestone | Theme | Ships | Gates on |
|-----------|-------|-------|----------|
| **v0.1** | The engine + 5 mocks | One-command stateful MCP mocks, seed/reset determinism, isolation, fault injection, trace emission, `payments`+`crm`+`exchange`+`email`+`files` | stampede v0.1 (for trace-format + demo needs) |
| **v0.2** | The moat | Registry + `add`, record-mode scaffolding, world composition | v0.1 stable schema |
| **v0.3** | The ecosystem | Deep stampede integration (`MockworldTarget` + control plane + trace nesting), scenario snapshots, contract-verify | stampede Target interface frozen |

---

## 2. Work breakdown structure (epics → tasks)

### EPIC A — Engine core (v0.1) · **L**
| Task | Detail | REQ | Size | Dep |
|------|--------|-----|:----:|-----|
| A1 | Project scaffold, packaging (uv/hatch), CLI skeleton (`run`/`list`/`reset`/`inspect`) | RT-1,3,4,10 | S | — |
| A2 | MCP exposure layer on FastMCP: `initialize`, `tools/list`, `tools/call`, stdio + Streamable HTTP | MCP-1,2 | M | A1 |
| A3 | `DeterministicContext`: seeded clock, id-gen, RNG, fault-dice substreams | DET-1..4 | M | A1 |
| A4 | State store: `StateStore` API, `MemoryStore`, `SQLiteStore` + conformance tests | STATE-1..3 | M | A3 |
| A5 | Session Manager: copy-on-write overlays keyed on `Mcp-Session-Id` | ISO-1..5, MCP-3 | M | A2,A4 |
| A6 | Behavior Dispatcher: declarative CRUD + Python handler ABI | DEF-1..4 | M | A3,A4 |
| A7 | Fault Injector: taxonomy, probability + conditional triggers, profiles, seeded dice | FAULT-1..7 | M | A3,A6 |
| A8 | Schema loader + validator (`schema_version`, pydantic models) | DEF-2,5 | S | A6 |
| A9 | `reset(seed)` ≡ restart; control API in-proc + HTTP | DET-5,6, CTL-1,2 | S | A5,A7 |

### EPIC B — Observability (v0.1) · **S–M**
| Task | Detail | REQ | Size | Dep |
|------|--------|-----|:----:|-----|
| B1 | Consume trace-format from stampede; target-side span emitter | OBS-1,2 | S | stampede trace-format |
| B2 | Trace nesting via propagated trace_id/parent span | OBS-2, STAMP-3 | S | B1 |
| B3 | NDJSON sink (default) + `--record-trace`; OTLP export (stretch) | OBS-3,4 | S | B1 |

### EPIC C — Built-in mock library (v0.1) · **L** (see §3 for order)
| Task | Detail | REQ | Size |
|------|--------|-----|:----:|
| C1 | `mock:payments` (marquee) | DEF-*, FAULT-* | M |
| C2 | `mock:crm` (misuse demo) | DEF-*, FAULT-* | S |
| C3 | `mock:exchange` (finance hook) | DEF-*, FAULT-* | M |
| C4 | `mock:email` | DEF-*, FAULT-* | S |
| C5 | `mock:files` | DEF-*, FAULT-* | S |
| C6 | Shared error library (`card_declined`, etc.) + fault profiles per mock | FAULT-2,5 | S |

### EPIC D — Authoring DX (v0.1 stretch → v0.2) · **S–M**
| Task | Detail | REQ | Size |
|------|--------|-----|:----:|
| D1 | `mockworld validate` linter (schema, handler sig, entropy smells, description quality) | DEF-6 | S |
| D2 | Fidelity checklist convention (`fidelity.md` + `fidelity:` field) | DEF-7 | XS |
| D3 | Authoring guide + `mock:hello` template + cookiecutter | DX-2 | S |

### EPIC E — Registry (v0.2) · **M**
| Task | Detail | REQ | Size |
|------|--------|-----|:----:|
| E1 | `registry.json` index-as-repo; `add`/`search`/pin/version | REG-1,2 | M |
| E2 | Provenance: checksum + signature | REG-3 | S |
| E3 | Sandboxed handler execution for registry mocks (subprocess/restricted) | REG-3, NFR-SEC-1 | M |

### EPIC F — Record-mode (v0.2) · **M**
| Task | Detail | REQ | Size |
|------|--------|-----|:----:|
| F1 | OpenAPI → declarative scaffold | REC-1 | S |
| F2 | Traffic capture → shape inference + PII scrub | REC-1,2 | M |
| F3 | Contract-verify `--against <real>` (Pact-style drift check) | REC-3 | M (v0.3) |

### EPIC G — World composition (v0.2) · **M**
| Task | Detail | REQ | Size |
|------|--------|-----|:----:|
| G1 | `world.yaml` compose several mocks | WORLD-1 | S |
| G2 | Shared identity namespace + coherent seeded dataset | WORLD-2 | M |

### EPIC H — Deep stampede integration (v0.3) · **M**
| Task | Detail | REQ | Size |
|------|--------|-----|:----:|
| H1 | Control-plane API finalized against stampede Target interface | STAMP-1, CTL-1 | S |
| H2 | `MockworldTarget` adapter (co-developed with stampede) | STAMP-1,2 | M |
| H3 | `stampede.yaml` drives reset(seed) + mockworld faults | STAMP-2,4 | S |
| H4 | End-to-end trace nesting verified in an Agent Readiness Report | STAMP-3 | S |

### EPIC I — Scenario snapshots (v0.3) · **S–M**
| Task | Detail | REQ | Size |
|------|--------|-----|:----:|
| I1 | `snapshot save/load` (SQLite-backed) w/ seed+versions embedded | SNAP-1,2 | S |
| I2 | State migrations across mock versions | DEF-8 | M |
| I3 | Shareable snapshot referenced by a stampede run for repro | SNAP-3 | S |

---

## 3. The 5 built-in mocks — prioritized by stampede's demo needs

| Order | Mock | Why this order (stampede-driven) | Effort | v0.1 tools (minimum) |
|:-----:|------|----------------------------------|:------:|----------------------|
| 1 | **mock:payments** | The hero demo & README GIF ("charge a fake card → realistic decline"). Highest star-driver. | M | `create_charge`, `capture_charge`, `refund_charge`, `get_charge`, `create_customer`, `get_customer` |
| 2 | **mock:crm** | Powers stampede's signature **misuse map** (delete-vs-archive) — the most screenshot-worthy Agent Readiness Report artifact. Small to build. | S | `create_record`, `get_record`, `update_record`, `archive_record`, `delete_record`, `list_records` |
| 3 | **mock:exchange** | The DeFi/finance hook; pairs with stampede's EVM/finance launch demos; brand-defining. | M | `get_balances`, `place_order`, `cancel_order`, `get_order`, `get_ticker` |
| 4 | **mock:email** | Universal side-effect; needed for multi-step "refund then notify" world stories. | S | `send_email`, `list_messages`, `get_message`, `search` |
| 5 | **mock:files** | Storage side-effect; read-after-write consistency demo. | S | `put_object`, `get_object`, `list_objects`, `delete_object` |

**Reordering vs. SPEC** (payments, email, exchange, crm, files): crm promoted 4→2 (misuse-map demo value); email demoted 2→4. Rationale in PRD §8. ⊕

---

## 4. Sequencing & dependencies

```
 stampede v0.1 (trace-format frozen, demo needs known)
        │
        ▼
 A1 → A2 → A3 → A4 → A5 ─┐
                A3 → A6 →A7→A9
        B1(needs trace-format) → B2 → B3
                          │
                          ▼
        C6 → C1 → C2 → C3 → C4 → C5        (mocks; C1 gates the launch GIF)
                          │
         D1,D2,D3 (DX, parallelizable with C*)
                          │
        ── v0.1 SHIP ──────────────────────────────
                          │
        E1→E2→E3   F1,F2   G1→G2             (v0.2, parallel epics)
                          │
        ── v0.2 SHIP ──────────────────────────────
                          │
        H1→H2→H3→H4   I1→I2→I3   F3           (v0.3)
                          │
        ── v0.3 SHIP ──────────────────────────────
```

**Critical path to launch:** A1→A2→A3→A4→A5→A6→A7 (engine) + B1 (trace) + C6→C1 (payments) + README GIF. Everything else in v0.1 can trail the hero demo.

**Hard external dependency:** B1 needs stampede's trace-format shape (RESEARCH Q1). Mitigation: build against a thin local `trace-format` shim matching the proposed shape (ARCHITECTURE §7.3); swap when stampede freezes it.

---

## 5. Effort roll-up

| Milestone | Epics | Rough effort (solo, alongside Xerberus) |
|-----------|-------|------------------------------------------|
| v0.1 | A (L) + B (S–M) + C (L) + D partial (S) | ~4–6 weeks |
| v0.2 | E (M) + F1,F2 (M) + G (M) | ~3–4 weeks |
| v0.3 | H (M) + I (S–M) + F3 (M) | ~3 weeks |

---

## 6. Definition of Done

### 6.1 Per feature
- Meets its REQ-ID(s); unit + integration tests green; determinism test passes (seed→identical); documented in the mock/authoring guide; no ambient-entropy lint violations.

### 6.2 Per built-in mock (acceptance)
- ≥ the minimum tool set (§3); agent-grade tool descriptions; stateful invariants enforced (e.g. refund ≤ captured); ≥3 signature faults declared + seed-reproducible; `fidelity.md` present; e2e scenario from TEST-PLAN passes; runs one-command over stdio + HTTP.

### 6.3 Per milestone
- **v0.1:** all P0 REQs met; 5 mocks pass acceptance; README GIF (agent charges fake card → seeded decline); `pip install mockworld` clean; determinism + isolation NFRs verified (byte-identical replay; 50 parallel sessions no cross-talk); trace emission consumed by a stampede run.
- **v0.2:** registry live with ≥1 external community mock added via PR; record-mode scaffolds a mock from an OpenAPI spec; a composed world runs.
- **v0.3:** a stampede run targets a mockworld world end-to-end with deterministic reset and nested traces in the Agent Readiness Report; a scenario snapshot reproduces a bug across machines.

---

## 7. Launch checklist (v0.1)

- [ ] README GIF above the fold (<90s): agent charges a fake card, gets a realistic seeded decline. **(hero artifact)**
- [ ] Quickstart ≤10 lines works copy-paste on a clean machine, offline.
- [ ] 5 built-in mocks pass acceptance; `mockworld list` shows them.
- [ ] Determinism promise provable in a one-liner demo (`reset --seed 42` twice → identical).
- [ ] 50-parallel-session isolation demo (CI matrix screenshot).
- [ ] Authoring guide + `mock:hello` template + one worked custom mock.
- [ ] `SPEC.md`/`ROADMAP.md`/`CITATION.cff`/`CONTRIBUTING.md` present; 3–5 seeded `good-first-issue`s (mostly "author mock:X").
- [ ] Sibling links + "Part of the Swarm Proof toolkit" table.
- [ ] Launch narrative bundled with stampede ("simulate the users **and** the world").
- [ ] **Joint stampede demo (agreed cross-project artifact):** stampede kills an agent mid-`create_charge` (transport fault) *while* mockworld throws a `card_declined` (business fault) → assert the charge fired **exactly once** (hooks `exactly-once`). Recovery asserted across both fault layers, one nested trace. This is the strongest chaos demo either project has — co-owned with stampede for the joint launch.
- [ ] Posts: HN "Show HN: I built a fake internet so my agents can't hurt anyone"; X thread w/ decline GIF; r/mcp; Trust Layer issue "why agents need a sandboxed world."
- [ ] One paired Trust Layer essay drafted.

---

## 8. Risks to delivery

| Risk | Impact | Mitigation |
|------|--------|-----------|
| trace-format not frozen by v0.1 | Blocks B1 | Build against the proposed shim; co-schedule with stampede architect (in flight) |
| Determinism leaks (a handler reads wall-clock) | Breaks the core promise | `mockworld validate` lints entropy; conformance test suite; ADR-4 |
| Two state-store impls diverge | Subtle nondeterminism | Shared `StateStore` conformance suite runs both |
| Fidelity debates ("real Stripe does X") | Bikeshedding, scope creep | `fidelity.md` per mock; "realistic enough to break agents correctly" bar; community owns long-tail |
| Registry handler code = RCE surface | Security | v0.1 = local-trusted only; v0.2b sandboxes before untrusted handlers run (ADR-7) |
| Scope creep toward vendor-exact clones | Endless work | NG2 non-goal enforced in review; per-mock scope frozen at §3 minimums |
