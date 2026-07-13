# mockworld — Design Specification & PRD
### A synthetic internet for agents
*Companion to stampede · v1.0 spec*

> **mockworld** — the localhost for the agent economy. Spin up high-fidelity fake services — a fake Stripe, a fake Gmail, a fake exchange, a fake CRM — as instant MCP servers, so you can build and test agents without touching production, leaking data, or paying for real API calls.

---

## 1. PRD

### 1.1 Problem

Anyone building or testing agents faces the same wall: agents need to *do things* — charge a card, send an email, place a trade, update a record — but you can't point a half-finished, non-deterministic agent at real Stripe/Gmail/an exchange during development and testing. So teams hand-build bespoke mocks for every project (narrow, throwaway, inconsistent) or test against nothing and discover failures in production. There's no general-purpose, high-fidelity, agent-native set of fake services. Benchmarks like tau-bench include narrow hand-built mocks; nothing reusable and broad exists.

### 1.2 Why it wins

- **Universal weekly pain:** every agent team needs safe fake services constantly. High-frequency utility = high stars + high retention.
- **Perfect companion to stampede:** stampede simulates the *users* (agents); mockworld simulates the *world* they act on. Neither requires the other, but together they're a complete agent test harness — and each drives adoption of the other.
- **Agent-native, not human-native:** unlike Postman mock servers or WireMock (built for human-driven API testing), mockworld services are exposed as MCP servers with realistic tool descriptions, stateful behavior, and injectable failure modes — the things agents actually stress.
- **Trust-brand fit:** "test agents that move money without touching real money" is squarely on-thesis.

### 1.3 Users & JTBD

1. **Agent developers** — "Give me a fake payments API my agent can actually transact against in tests." (Primary.)
2. **stampede users** — "I need a realistic world for my simulated swarm to act on."
3. **CI pipelines** — "Deterministic, resettable fake services so agent tests are reproducible."
4. **Educators / demos** — "A safe sandbox to teach agent building."

### 1.4 Goals & non-goals

**Goals (v0.1):** a library of high-fidelity mock services, each runnable as an MCP server with one command; realistic stateful behavior (a fake Stripe that tracks balances, refunds, disputes); resettable, seedable state for reproducible tests; injectable failures (declines, rate limits, latency, partial outages); a simple schema to author *new* mocks. Ship the 3–4 mocks stampede's own demos need first.

**Non-goals:** being a production API gateway; perfectly replicating any real vendor's full surface (fidelity where it matters for agents, not 100% coverage); record/replay of real traffic (possible later).

### 1.5 Success metrics

- Stars driven by the "fake Stripe for agents in one command" hook.
- North star: number of mock services in the community registry + number of projects depending on mockworld in tests.
- ≥10 community-contributed mocks within 90 days (the registry is the moat).

---

## 2. ARCHITECTURE

### 2.1 Shape

```
┌────────────────────────────────────────────────────────┐
│                     mockworld runtime                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ mock:stripe  │  │  mock:gmail  │  │ mock:exchange│ …  │  ← each = an MCP server
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│         │                 │                 │           │
│  ┌──────────────────────────────────────────────────┐  │
│  │   Shared engine: state store · fault injector ·   │  │
│  │   MCP exposure · reset/seed · record              │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
        agents / stampede swarm connect via MCP  ▲
```

### 2.2 Components

**A. Mock definition format** — each mock is declarative + optional Python for complex logic:
```yaml
name: stripe
description: "Fake Stripe. Charge, refund, dispute — with realistic balances and errors."
state:
  customers: {}
  charges: {}
tools:
  - name: create_charge
    description: "Charge a customer's card. amount in cents."
    params: {customer_id: str, amount: int, currency: str}
    behavior: python:handlers.create_charge      # logic that mutates state realistically
    faults:                                       # injectable, probabilistic
      - card_declined: 0.05
      - rate_limited: 0.02
      - latency_ms: {p50: 80, p99: 1200}
```

**B. Shared engine** — one runtime that: hosts any mock as an MCP server (stdio or HTTP/SSE); manages per-session state (isolated, so parallel test runs don't collide); exposes `reset(seed)` for deterministic tests; drives the fault injector (declines, rate limits, latency, outages) so agents face realistic adversity; records all interactions in the shared trace format.

**C. The mock library (v0.1 built-ins)** — prioritized by (a) stampede's demo needs and (b) universality:
1. `mock:payments` (Stripe-shaped) — the marquee.
2. `mock:email` (Gmail/SMTP-shaped) — send/read/search.
3. `mock:exchange` (CEX-shaped) — balances, orders, fills, slippage — the DeFi/finance hook.
4. `mock:crm` (records to create/update/delete — powers stampede's "delete vs archive" misuse demo).
5. `mock:files` (S3-shaped storage).

**D. Registry** — a simple index (like awesome-lists → package registry) where the community publishes mocks; `mockworld add mock:shopify` pulls one. The registry is the network effect.

### 2.3 Tech stack

Python 3.11+; official MCP SDK for exposure; pluggable state store (in-memory default, SQLite for persistence, isolated per session); FastAPI for HTTP transport; fault injection as middleware; provider-agnostic (mocks are LLM-free — they're deterministic services, which is the point).

### 2.4 Risks & mitigations

- **"Just use WireMock/Postman"** → those are human-API-testing tools with no MCP exposure, no agent-realistic tool descriptions, and no agent-native fault semantics; lead with the MCP-native + stateful-behavior differentiators.
- **Fidelity debates ("real Stripe does X differently")** → explicitly scope to "realistic enough to break agents correctly," not vendor-exact; community mocks handle long-tail fidelity.
- **Maintenance surface (many mocks)** → the declarative format keeps each mock small; registry offloads long-tail to the community.

---

## 3. ROADMAP

- **v0.1:** engine + 5 built-in mocks + one-command run + reset/seed + fault injection. Ships alongside stampede's first EVM/finance demos.
- **v0.2:** registry + `mockworld add`; record-mode (capture a real API's shapes to scaffold a mock); mock composition (a "world" = several mocks with shared state).
- **v0.3:** deep stampede integration (`stampede` targets a `mockworld` world directly); scenario snapshots (a seeded world state you can share for reproducible bug reports).

## 4. LAUNCH

Hook: "I built a fake internet so my agents can't hurt anyone." HN Show, X thread with a GIF of an agent charging a fake card and getting a realistic decline, r/mcp, and a Trust Layer issue on "why agents need a sandboxed world." Bundle the launch narrative with stampede ("simulate the users *and* the world").
