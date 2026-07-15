# mockworld

### A synthetic internet for agents

> The localhost for the agent economy. Spin up high-fidelity fake services — a fake Stripe, a fake Gmail, a fake exchange, a fake CRM — as instant MCP servers, so you can build and test agents without touching production, leaking data, or paying for real API calls.

<!-- TODO: demo GIF — an agent charging a fake card and getting a realistic decline -->
<p align="center"><em>▶ demo GIF coming — an agent transacts against a fake Stripe and hits a realistic decline</em></p>

> **Status:** 🟢 v0.1 engine + 5 built-in mocks implemented (deterministic core, MCP stdio+HTTP, fault injection, control plane, stampede `Target`). Companion to [stampede](https://github.com/swarmproof/stampede).

---

## Why

Agents need to *do things* — charge a card, send an email, place a trade, update a record — but you can't point a half-finished, non-deterministic agent at real Stripe/Gmail/an exchange during development. So teams hand-build throwaway mocks for every project, or test against nothing and find failures in production.

The 2026 crop of agent sandboxes (Veris Sandbox, AWS ToolSimulator) fills that gap by putting an **LLM in the response path** — convenient, but it means your mock never behaves the same way twice. A stochastic mock can't give you a CI run that's green for the same reason twice, a byte-identical bug repro, or an offline/air-gapped test.

mockworld takes the opposite bet — **deterministic, MCP-native, open:**

- **Deterministic & LLM-free.** A seed fully determines state, IDs, timing, and every injected fault. `reset --seed 42` produces the *same* decline, every time, across 50 parallel CI workers. No LLM in the hot path, ever — that's the moat, not a footnote.
- **MCP-native & agent-realistic.** Services are real MCP servers with agent-grade tool descriptions, stateful behavior, and *business-logic* fault semantics (declines, insufficient funds, rate limits, disputes) — the things agents actually stress. (Postman/WireMock are built for human-driven HTTP testing; they don't speak MCP and can't model business state.)
- **Open & self-hostable.** `pip install`, runs on your laptop, offline, free, Apache-2.0 — not a hosted SaaS.

## Quickstart

```bash
pip install mockworld                 # (from source until first PyPI cut: pip install -e ".[dev]")

mockworld list                        # the 5 built-in mocks
mockworld run mock:payments           # a stateful fake Stripe as an MCP (stdio) server
mockworld run mock:payments --transport http --port 8931   # Streamable HTTP + control plane
mockworld run mock:payments --seed 42 --faults hostile     # deterministic + adversarial
mockworld inspect mock:crm            # tools, faults, and state shape without running
mockworld demo mock:payments          # prove determinism: same seed → identical transcript
```

Point any MCP client (or a [stampede](https://github.com/swarmproof/stampede) swarm) at it. `reset --seed 42` returns a running server to a byte-identical world, every time.

## What's inside (v0.1 built-ins)

`mock:payments` (Stripe-shaped, the marquee) · `mock:email` (Gmail/SMTP) · `mock:exchange` (balances, orders, fills, slippage) · `mock:crm` (records — powers the "delete vs archive" misuse demo) · `mock:files` (S3-shaped). A declarative schema lets you author new mocks; the **registry** (`mockworld add mock:shopify`) is the network effect.

See [`SPEC.md`](./SPEC.md) and [`ROADMAP.md`](./ROADMAP.md).

## Part of the Swarm Proof toolkit

*Trust infrastructure for the agent economy — seven projects, one thesis.*

| Project | What it does |
|---------|--------------|
| [stampede](https://github.com/swarmproof/stampede) | Point a herd of realistic agents at your system before real ones arrive |
| **mockworld** ← *you are here* | A synthetic internet for agents — fake Stripe, Gmail, exchange, instantly |
| [mcp-probe](https://github.com/swarmproof/mcp-probe) | The CI quality suite for MCP servers — lint, contract-test, benchmark, load |
| [costbomb](https://github.com/swarmproof/costbomb) | Denial-of-wallet fuzzing — find the inputs that make your agent spend $500 |
| [exactly-once](https://github.com/swarmproof/exactly-once) | Idempotency middleware so agent side-effects fire once |
| [agent-postmortems](https://github.com/swarmproof/agent-postmortems) | A structured incident database + post-mortem standard for agent failures |
| [awesome-agent-reliability](https://github.com/swarmproof/awesome-agent-reliability) | The curated map of the field |

## License

[Apache-2.0](./LICENSE). Mocks are LLM-free — deterministic services by design. Citable via [`CITATION.cff`](./CITATION.cff).
