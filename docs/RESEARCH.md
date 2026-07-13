# mockworld — RESEARCH

*Problem, 2026 landscape, prior art, users & jobs, use-case catalog, gap analysis, positioning.*
*Companion research doc to `SPEC.md`. Author: mockworld architect. Last updated: 2026-07-13.*

> Legend: **⊕ Beyond original spec** marks findings/recommendations that extend the v1.0 `SPEC.md`.

---

## 1. The thesis, sharpened

The spec's one-liner — *"a synthetic internet for agents"* — is correct but under-specified against the 2026 landscape. After research, the defensible thesis is narrower and sharper:

> **mockworld is the deterministic, LLM-free, open-source, MCP-native sandbox for the tools agents act on.** It is to *the world an agent touches* what a mainnet fork is to a smart contract: a local, resettable, seedable, fault-injectable replica you can hammer without consequences and re-run bit-for-bit.

Three load-bearing claims, each pressure-tested below:

| Claim | Why it survives scrutiny | The trap it avoids |
|-------|--------------------------|--------------------|
| **Deterministic & LLM-free** | Reproducible CI and shareable bug repros require byte-identical replay from a seed. An LLM in the response path makes that structurally impossible. | The 2026 category leaders (Veris, ToolSimulator) put an LLM in the response path — convenient, but non-reproducible. |
| **MCP-native, agent-realistic** | Agents consume *tool descriptions*, not OpenAPI. The failure surface is "misread the description / picked the wrong tool," which only exists if the mock ships agent-grade descriptions and MCP semantics. | Generic HTTP mockers (WireMock, Prism) have no MCP layer and no concept of tool legibility. |
| **Stateful & fault-injectable** | The interesting agent failures are *stateful* ("refund exceeds captured amount", "insufficient funds after prior order") and *adversarial* (declines, rate limits, partial outages). | Stateless spec-mockers (Prism) can't produce these; transport chaos tools (Toxiproxy) can't produce *business-logic* faults. |

**The refinement that matters most:** the spec frames the competition as "not WireMock/Postman." That was true when the spec was written. As of 2026 the *real* competition is the new **LLM-powered agent-sandbox** category (§3.2). mockworld's wedge is not "MCP-native vs. human-native" — it is **"deterministic & self-hostable vs. stochastic & hosted."** This reframing runs through every doc.

---

## 2. Why now (2026)

- **The category the spec anticipated actually formed — and split.** "Sandbox for agents" is now a named product category. It bifurcated into (a) *code-execution* sandboxes (Fly.io agent-sandbox, E2B, Modal, Cloudflare dynamic workers, AIO Sandbox) that isolate *the agent's compute*, and (b) *tool/environment* simulators (Veris, AWS ToolSimulator/Strands Evals) that fake *the services the agent calls*. mockworld lives squarely in (b) — and is the only credible **deterministic, open-source** entrant there.
- **MCP won the interface war and standardized statefulness.** The MCP spec's Streamable HTTP transport (superseding SSE) assigns a session via the `Mcp-Session-Id` header at `initialize` time. That gives mockworld a *standard* hook for per-session state isolation — we don't have to invent a session model, we ride MCP's. FastMCP (PrefectHQ) + the official `modelcontextprotocol/python-sdk` make one-command stateful MCP servers a decorator away.
- **Benchmarks proved the value but not the reusability.** τ-bench / τ²-bench (Sierra) demonstrated that *stateful, policy-governed mock domains* (retail, airline, telecom) are the right shape for evaluating tool-agents — τ²-bench even models the domain as a Dec-POMDP with a compositional task generator. But each domain is hand-built and bench-specific. mockworld generalizes exactly this into reusable, composable, installable services. **τ-bench is the proof of demand; mockworld is the productization.**
- **OpenAI Agents SDK (Apr 2026 overhaul) made MCP + sandboxes first-class**, pulling thousands of new builders into "how do I test my agent's tools safely" — a rising tide for the whole category.

---

## 3. Competitive & adjacent landscape (named + URLs)

### 3.1 Human-API mocking (the *old* comparison set) — adjacent, not competitive

| Tool | What it is | Stateful? | MCP-native? | Agent-native faults? | Gap vs. mockworld |
|------|-----------|:---------:|:-----------:|:--------------------:|-------------------|
| **WireMock** ([wiremock.org](https://wiremock.org/)) | Language-agnostic HTTP mock server; record-and-replay; rich matching | Partial (scenario state machines) | ✗ | ✗ (HTTP fault only: bad response, delay) | No MCP; no tool descriptions; faults are HTTP-level, not business-level |
| **Mockoon** ([qaskills.sh guide](https://qaskills.sh/blog/mockoon-api-mocking-tool-guide)) | Visual desktop mock; Handlebars templating; OpenAPI import | Weak | ✗ | ✗ | Human-first GUI; no agent semantics |
| **Prism** (Stoplight) | Mock server generated from OpenAPI | **✗ stateless by design** | ✗ | ✗ | Cannot model workflows that depend on prior calls — disqualifying for agents |
| **MSW** (Mock Service Worker) | Browser/Node request interception for FE tests | Test-scoped | ✗ | ✗ | Interception layer, not a hostable stateful world |
| **MockServer / Mountebank** | Programmable mock + proxy; multi-protocol | Yes | ✗ | Partial | Mature but human-test oriented; no MCP, no tool legibility |

**Verdict:** these are complements and pattern-donors (record-and-replay, matching, scenario state), not competitors. mockworld should *borrow their record-mode ergonomics* and *reject their human-API framing*. Sources: [ASOasis 2026 comparison](https://asoasis.tech/articles/2026-04-05-0252-api-mocking-tools-comparison/), [MG Software mocking tools](https://www.mgsoftware.nl/en/tools/best-api-mocking-tools).

### 3.2 Agent-native tool/environment simulators (the *real* competition — 2026)

| Tool | Approach | Deterministic? | Open source? | Delivery | MCP | Verdict |
|------|----------|:--------------:|:------------:|----------|:---:|---------|
| **Veris Sandbox** ([veris.ai/sandbox](https://veris.ai/sandbox)) | **LLM-powered** mock services, 50+ integrations (Salesforce, Zendesk, Stripe, banking); scenario gen, A/B, CI gates, RL reward data | ✗ (LLM in response path; markets "Determinism" as a feature but stochastic core) | ✗ (hosted SaaS, console.veris.ai) | Cloud SaaS | Unclear | **Primary competitor.** Richer product, but closed, hosted, and non-reproducible by construction. |
| **AWS ToolSimulator** (Strands Evals) ([AWS blog](https://aws.amazon.com/blogs/machine-learning/toolsimulator-scalable-tool-testing-for-ai-agents/)) | **LLM-powered** tool response generation; state via `share_state_id`; Pydantic schema enforcement | ✗ (explicitly: "LLM-generated responses inherently introduce variability") | Partial (in Strands ecosystem) | Library | Mentioned | **Closest technical analog.** Confirms the pattern *and* the deterministic gap we exploit. |
| **τ-bench / τ²-bench** ([github.com/sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench)) | Hand-built stateful domains (retail/airline/telecom) as eval envs; Dec-POMDP; compositional task gen | ✓ (code-defined) | ✓ | Research code | ✗ | **Proof of demand, not a product.** Not reusable/installable/composable. mockworld = the general-purpose version. |

`★ The single most important research finding ─────────`
The agent-sandbox category converged on **LLM-generated tool responses** because it's fast to build and "realistic-feeling." But that choice **forfeits determinism, reproducibility, offline/air-gapped CI, cost-free operation, and shareable bug repros.** mockworld's LLM-free stance — framed in the spec as a footnote ("mocks are LLM-free by design") — is actually the **core competitive moat.** Every doc leads with it.
`──────────────────────────────────────────────────`

### 3.3 Code-execution sandboxes — adjacent (isolate the agent, not the world)

[Fly.io agent-sandbox](https://fly.io/learn/agent-sandbox/), [E2B](https://e2b.dev), [Modal](https://modal.com/resources/best-code-execution-sandboxes-ai-agents), Cloudflare dynamic workers, [AIO Sandbox](https://sandbox.agent-infra.com/) (browser+shell+FS+MCP hub in one container). These isolate *where the agent runs*. mockworld is **complementary**: run your agent inside E2B/Fly, point it at a mockworld world for its tools. **⊕ Integration opportunity:** ship a mockworld container that drops into AIO Sandbox's MCP hub.

### 3.4 Fault injection / chaos — pattern donors, layered below us

[Toxiproxy](https://grokipedia.com/page/Toxiproxy) (Shopify — TCP proxy: latency, drops, bandwidth), Istio fault injection (network-layer abort/delay), Gremlin, Chaos Mesh, LitmusChaos. These operate at **transport/infra layers**. mockworld's faults are **application/business-logic** (`card_declined`, `insufficient_funds`, `refund_exceeds_charge`, `rate_limited`). **This is the clean seam with stampede** (§6): stampede's Chaos Injector owns transport faults, mockworld owns semantic faults. Source: [Total Shift Left 2026](https://totalshiftleft.ai/blog/fault-injection-testing-explained).

### 3.5 Contract testing — a v0.2+ convergence opportunity ⊕

[Pact](https://docs.pact.io/) (consumer-driven contracts), Keploy (traffic-derived contracts), Prism (schema-first). Key insight from research: *"mocks drift unless generated from verified contracts or governed by a disciplined lifecycle."* This is a real risk for mockworld's fidelity claim. **⊕ Opportunity:** mockworld's record-mode (v0.2) should emit an artifact that can be contract-verified against the real provider (a `mockworld verify --against real-stripe` story), turning drift from a weakness into a governed feature. Sources: [Total Shift Left contract testing](https://totalshiftleft.ai/blog/what-is-api-contract-testing), [Keploy tools](https://keploy.io/blog/community/contract-testing-tools).

---

## 4. Prior art summary

- **Service virtualization lineage** (WireMock, Mountebank, MockServer, IBM/Broadcom SV): decades of "fake the dependency" tooling — all human/HTTP-oriented. mockworld inherits their *techniques* (matching, record-replay, scenario state, stateful proxies) and rejects their *audience*.
- **Benchmark-embedded mocks** (τ-bench, WebArena, AppWorld, SWE-bench harnesses): each proves stateful mock worlds are essential for agent evaluation, each rebuilds them bespoke. The reusability gap is the product gap.
- **Sandbox-as-a-product precedent** the spec cites (MiroFish → stampede): the "watchable society, one command" pattern. For mockworld the analog is *"fake service, one command, realistic decline."*
- **The determinism lineage** (mainnet forks / Anvil, VCR/cassettes, `responses`/`httpretty`, Polly.js record-replay): the developer expectation that a dependency can be frozen and replayed. mockworld brings that expectation to the MCP era.

---

## 5. Users & Jobs-To-Be-Done (expanded from spec §1.3)

The spec lists 4 users. Research supports **7 distinct JTBD**, ranked by pull:

| # | Persona | Job (JTBD) | Trigger | Success looks like | Priority |
|---|---------|-----------|---------|--------------------|:--------:|
| P1 | **Agent developer** (primary) | "Give me a fake payments/email/exchange API my agent can actually transact against while I build." | Building an agent that must take real-world actions | `mockworld run mock:payments`, agent charges a fake card in <2 min | P0 |
| P2 | **stampede user** (sibling) | "Give my simulated swarm a realistic, resettable world to act on." | Running a stampede simulation that needs side-effects | `MockworldTarget` boots a world; swarm transacts; deterministic reset per run | P0 |
| P3 | **CI / test engineer** | "Deterministic, isolated, resettable fake services so agent tests are reproducible and parallel-safe." | Agent test suite flakes / hits real APIs | Seeded run is byte-identical; 50 parallel test workers don't collide | P0 |
| P4 | **Agent-reliability / red-teamer** | "Inject realistic adversity (declines, rate limits, partial outages) and see if my agent degrades gracefully." | Hardening an agent before launch | Fault scenario reproducibly triggers the failure; agent handling observed | P1 |
| P5 | **Educator / demo author** | "A safe, offline sandbox to teach agent building without API keys or spend." | Workshop, tutorial, conference demo | Zero-credential, zero-cost, offline `mockworld run`; students can't hurt anything | P1 |
| P6 | **Mock author / community contributor** ⊕ | "Author a new high-fidelity mock (my SaaS, my protocol) with minimal code and publish it." | Wants their service testable by agents; wants registry presence | YAML + optional Python handler; `mockworld publish`; appears in registry | P1 (moat) |
| P7 | **Framework / platform team** ⊕ | "Ship mockworld worlds as fixtures in our agent framework's test kit." | LangGraph/CrewAI/etc. wants an official test harness | mockworld importable as a pytest fixture / framework adapter | P2 |

**⊕ New personas vs. spec:** P6 (mock author — the registry flywheel depends on this persona having a first-class authoring DX) and P7 (framework integrator — distribution channel).

---

## 6. The stampede ↔ mockworld relationship (research-level; contract in ARCHITECTURE.md)

stampede simulates the **users** (agent population); mockworld simulates the **world** (services). They are orthogonal and each drives the other's adoption. Research confirms the seam:

```
   stampede swarm  ──drives──▶  mockworld world
   (the agents)                 (the services)
        │                              │
   Chaos Injector              Fault Injector
   TRANSPORT faults            SEMANTIC faults
   (kill, timeout,             (card_declined,
    malformed frame,            insufficient_funds,
    latency, dropped conn)      rate_limited, dispute)
        │                              │
        └──────── both nest into ──────┘
              ONE trace_id (trace-format)
        agent-side spans  ⊃  target-side spans
```

- **Fault-layer split** (the important one): stampede owns *transport/infra* chaos (its Chaos Injector — kills, timeouts, malformed frames), mockworld owns *application/business-logic* faults (its Fault Injector). No overlap; they compose. Confirmed clean by the Toxiproxy-vs-business-logic distinction in §3.4.
- **trace-format:** authored in stampede. mockworld is a **producer of target-side spans** that nest under stampede's agent-side spans via shared `trace_id`. mockworld does not redefine the schema.
- **Control-plane:** stampede must be able to drive `reset(seed)` and toggle mockworld faults *from `stampede.yaml`* so a run is self-contained and deterministic. → proposed `MockworldTarget` adapter + control-plane API (ARCHITECTURE.md §7).

*(Integration contract details, interface signatures, and open questions to the stampede architect are in `ARCHITECTURE.md §7`.)*

---

## 7. Comprehensive use-case catalog

Grouped by the *kind of agent failure* each exercises — because the failure is the product.

### 7.1 Stateful-correctness cases (agent must respect world state)
1. Charge a card, then refund — refund must not exceed captured amount (`mock:payments`).
2. Place an order that exceeds balance → `insufficient_funds` (`mock:exchange`).
3. Refund an already-refunded charge → idempotency / double-refund detection (ties to `exactly-once`).
4. Send email to a bounced address → permanent-bounce state persists across retries (`mock:email`).
5. Delete vs. archive a CRM record — the marquee "misuse" demo: does the agent destroy data it meant to hide? (`mock:crm`).
6. Read-after-write consistency: upload a file, immediately list — does it appear? (`mock:files`).
7. Order fills with slippage — agent's expected price ≠ fill price (`mock:exchange`).

### 7.2 Fault-resilience cases (agent must degrade gracefully)
8. Seeded 5% `card_declined` — does the agent retry sanely or loop?
9. `rate_limited` (429 + Retry-After) — does the agent back off or hammer?
10. Latency spike (p99 = 1200ms) — does the agent time out prematurely / duplicate the request?
11. Partial outage: `create_charge` works, `get_charge` fails — does the agent assume failure and double-charge?
12. Malformed/ambiguous error payload — does the agent misclassify a decline as a network error?

### 7.3 Determinism / reproducibility cases (CI & bug-repro)
13. `reset --seed 42` → identical state → identical agent transcript (snapshot test).
14. 50 parallel CI workers, each an isolated session, zero cross-talk.
15. Ship a **scenario snapshot** (seeded world state) in a bug report; maintainer reproduces exactly (v0.3).
16. Run-diffing: same seed, two agent versions → diff behavior, not noise.

### 7.4 Composition / world cases ⊕ (v0.2+)
17. A "world" = `payments + crm + email` sharing a customer_id namespace: agent refunds a charge, updates the CRM record, emails the customer — cross-service consistency.
18. Scenario library: "e-commerce world seeded with 100 customers, 30 disputes, 5 fraud flags."

### 7.5 stampede-driven cases (swarm × world)
19. 200-agent swarm transacts against `mock:payments`; report shows how many hit the seeded decline and how each persona handled it.
20. Adversarial cohort attempts denial-of-wallet against `mock:exchange` — costbomb hook.

### 7.6 Authoring / registry cases ⊕
21. Author `mock:shopify` from OpenAPI via record-mode scaffold, add stateful handler, `mockworld publish`.
22. `mockworld add mock:twilio` pulls a community mock; runs in one command.

---

## 8. Gap analysis

### 8.1 Field gaps (white space mockworld fills)
| Gap in the 2026 field | Who almost fills it | mockworld's fill |
|-----------------------|---------------------|------------------|
| **Deterministic** agent-tool sandbox | Veris/ToolSimulator (but LLM-stochastic) | LLM-free, seed→byte-identical replay |
| **Open-source, self-hostable, offline** | Veris (SaaS-only) | Apache-2.0, `pip install`, air-gapped |
| **MCP-native** stateful mock w/ agent-grade tool descriptions | WireMock/Prism (HTTP only) | First-class MCP tools + legibility-tuned descriptions |
| **Reusable, installable, composable** mock worlds | τ-bench (hand-built, bench-locked) | Declarative schema + registry + composition |
| **Business-logic fault injection** for agents | Toxiproxy (transport only) | Semantic faults as first-class, probabilistic, seedable |
| **Shareable scenario snapshots** for repro | — (nobody) | Seeded world state as a portable artifact (v0.3) |

### 8.2 Spec gaps (things `SPEC.md` under-specifies — resolved in these docs)
| # | Gap in v1.0 spec | Resolution doc |
|---|------------------|----------------|
| G1 | Session isolation model is asserted ("isolated per session") but not designed. How is a session keyed? | ARCHITECTURE §6 — key on MCP `Mcp-Session-Id`; copy-on-write state overlay |
| G2 | Determinism is claimed but the *sources of nondeterminism* (time, IDs, RNG, iteration order, fault dice) are not enumerated or controlled. | ARCHITECTURE §5.2 — deterministic clock/ID/RNG injected from seed |
| G3 | The mock-definition schema is sketched, not authoritative (no fault grammar, no state-migration, no handler contract, no versioning). | ARCHITECTURE §4 — authoritative schema + handler ABI |
| G4 | Fault semantics are examples, not a taxonomy (what faults exist, how they compose, how they're made deterministic). | ARCHITECTURE §5.3 + PRD REQ-FAULT-* |
| G5 | stampede integration is a v0.3 bullet with no contract (adapter shape, control plane, trace nesting). | ARCHITECTURE §7 — `MockworldTarget` + control-plane API |
| G6 | Registry is "a simple index" — no trust/versioning/security model for community-run code. | ARCHITECTURE §8 — index + signing + handler sandboxing |
| G7 | Record-mode is a v0.2 bullet with no design (capture from where? how much fidelity? PII?). | ARCHITECTURE §9 + PRD REQ-REC-* |
| G8 | No stated approach to **fidelity governance** (the "real Stripe does X differently" risk). | This doc §3.5 (contract-verify) + PRD non-goals |
| G9 | Missing features entirely: record-mode DX, world composition, scenario snapshots, session isolation guarantees, observability/trace emission, security of handler execution. | PRD feature tiers + ARCHITECTURE |

---

## 9. Differentiation & positioning

**Positioning statement:**
> *For agent developers and reliability engineers who need to build and test agents that take real-world actions, mockworld is an open-source, MCP-native sandbox of deterministic fake services (payments, email, exchange, CRM, files). Unlike LLM-powered sandboxes (Veris, ToolSimulator) that trade reproducibility for convenience, and unlike HTTP mockers (WireMock, Prism) built for humans, mockworld is byte-for-byte reproducible, fault-injectable, and self-hostable — the localhost for the agent economy.*

**The three-word wedge:** *deterministic. MCP-native. open.*

**Messaging ladder (what to lead with, by audience):**
- Developers → *"a fake Stripe your agent can charge, in one command, offline, free."*
- CI/reliability → *"seed 42 → the same decline, every time, in 50 parallel workers."*
- stampede users → *"simulate the users **and** the world."*
- Skeptics ("just use WireMock") → *"WireMock doesn't speak MCP, doesn't model business state, and can't decline a card the way that breaks your agent."*
- Skeptics ("just use Veris/ToolSimulator") → *"an LLM in your mock means your CI is never green twice for the same reason."*

**What we deliberately are NOT** (reinforced): a production API gateway; a vendor-exact clone; an agent *builder* or *evaluator* (that's stampede/agentevals); a hosted SaaS (v0.1); an LLM-in-the-loop simulator.

---

## 10. Open questions

| # | Question | Owner | Bearing on |
|---|----------|-------|-----------|
| Q1 | Exact trace-format span/attribute shape for **target-side** spans — awaiting stampede architect. | stampede | ARCHITECTURE §7, observability |
| Q2 | Registry: host as a GitHub-topic index (awesome-list style) first, or a real package index from day one? | mockworld | v0.2 scope, moat |
| Q3 | How is community handler code executed safely — subprocess/WASM/RestrictedPython? What's the v0.1 stance (trust local only)? | mockworld | §8 security |
| Q4 | Do we commit to **one** fidelity bar phrase — *"realistic enough to break agents correctly"* — as the governance North Star, and codify it as a per-mock fidelity checklist? | mockworld | fidelity debates |
| Q5 | State store default: pure in-memory (fastest, ephemeral) vs. SQLite (persistable, snapshot-friendly). Recommendation: in-memory default, SQLite backing for snapshots/persistence. | mockworld | ARCHITECTURE §5.1 |
| Q6 | Should record-mode (v0.2) emit a **Pact-style contract** so mocks can be drift-verified against the real provider? (§3.5) | mockworld | fidelity governance |
| Q7 | Composition namespace model: do composed mocks share one ID space (a `customer_id` known to payments+crm+email) or federate via explicit links? | mockworld | v0.2 world composition |

---

*Sources consulted (2026): [WireMock](https://wiremock.org/) · [ASOasis mocking comparison](https://asoasis.tech/articles/2026-04-05-0252-api-mocking-tools-comparison/) · [Mockoon guide](https://qaskills.sh/blog/mockoon-api-mocking-tool-guide) · [Veris Sandbox](https://veris.ai/sandbox) · [AWS ToolSimulator](https://aws.amazon.com/blogs/machine-learning/toolsimulator-scalable-tool-testing-for-ai-agents/) · [τ²-bench](https://github.com/sierra-research/tau2-bench) · [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/) · [MCP transports spec](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) · [FastMCP](https://github.com/PrefectHQ/fastmcp) · [Cloudflare streamable HTTP MCP](https://blog.cloudflare.com/streamable-http-mcp-servers-python/) · [Fly.io agent sandbox](https://fly.io/learn/agent-sandbox/) · [AIO Sandbox](https://sandbox.agent-infra.com/) · [Toxiproxy](https://grokipedia.com/page/Toxiproxy) · [Total Shift Left fault injection](https://totalshiftleft.ai/blog/fault-injection-testing-explained) · [Pact docs](https://docs.pact.io/) · [Contract testing tools](https://keploy.io/blog/community/contract-testing-tools) · [OpenAI Agents SDK 2026](https://aiautomationglobal.com/blog/openai-agents-sdk-sandbox-native-agent-primitives-2026).*
