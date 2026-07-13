# mockworld

### A synthetic internet for agents

> The localhost for the agent economy. Spin up high-fidelity fake services — a fake Stripe, a fake Gmail, a fake exchange, a fake CRM — as instant MCP servers, so you can build and test agents without touching production, leaking data, or paying for real API calls.

<!-- TODO: demo GIF — an agent charging a fake card and getting a realistic decline -->
<p align="center"><em>▶ demo GIF coming — an agent transacts against a fake Stripe and hits a realistic decline</em></p>

> **Status:** 🚧 v0.1 planned (Q2). Companion to [stampede](https://github.com/swarmproof/stampede).

---

## Why

Agents need to *do things* — charge a card, send an email, place a trade, update a record — but you can't point a half-finished, non-deterministic agent at real Stripe/Gmail/an exchange during development. So teams hand-build throwaway mocks for every project, or test against nothing and find failures in production. There's no general-purpose, high-fidelity, **agent-native** set of fake services.

Unlike Postman/WireMock (human-driven API testing), mockworld services are exposed as MCP servers with realistic tool descriptions, stateful behavior, and injectable failure modes — the things agents actually stress.

## Quickstart

```bash
pip install mockworld
mockworld run mock:payments          # a stateful fake Stripe as an MCP server
mockworld run mock:email --port 8931 # send/read/search
mockworld reset --seed 42            # deterministic state for reproducible tests
```

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
