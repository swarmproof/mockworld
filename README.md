<div align="center">

# mockworld

### A synthetic internet for agents

Run fake services — a fake Stripe, a fake Gmail, a fake exchange, a fake CRM — as local [MCP](https://modelcontextprotocol.io) servers, so you can build and test agents without touching production, leaking data, or paying for real API calls.

[![PyPI](https://img.shields.io/pypi/v/mockworld-mcp.svg)](https://pypi.org/project/mockworld-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/mockworld-mcp.svg)](https://pypi.org/project/mockworld-mcp/)
[![CI](https://github.com/swarmproof/mockworld/actions/workflows/ci.yml/badge.svg)](https://github.com/swarmproof/mockworld/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)

</div>

```bash
pip install mockworld-mcp
mockworld run mock:payments      # a stateful fake Stripe as an MCP server
```

> **Status:** released — `mockworld-mcp` on PyPI. Deterministic engine, 6 built-in mocks, MCP stdio + HTTP, fault injection, control plane, registry, world composition, record-mode, snapshots, and a stampede `Target`. Companion to [stampede](https://github.com/swarmproof/stampede).

---

## Contents

- [Why](#why)
- [Install](#install)
- [Quickstart](#quickstart)
- [Use it in your tests](#use-it-in-your-tests)
- [Built-in mocks](#built-in-mocks)
- [Author & share mocks](#author--share-mocks)
- [Compose, record, and simulate](#compose-record-and-simulate)
- [Project structure](#project-structure)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)
- [Part of the Swarm Proof toolkit](#part-of-the-swarm-proof-toolkit)

## Why

Agents need to *do things* — charge a card, send an email, place a trade, update a record — but you can't point a half-finished, non-deterministic agent at real Stripe/Gmail/an exchange during development. So teams hand-build throwaway mocks for every project, or test against nothing and find failures in production.

Recent agent sandboxes (Veris Sandbox, AWS ToolSimulator) put an **LLM in the response path**, so the mock does not behave the same way twice. That rules out a CI run that is green for the same reason twice, a byte-identical bug repro, and offline or air-gapped testing.

mockworld is deterministic, MCP-native, and open:

- **Deterministic & LLM-free.** A seed determines state, IDs, timing, and every injected fault. `reset --seed 42` produces the same decline across 50 parallel CI workers. No LLM in the response path.
- **MCP-native.** Services are MCP servers with tool descriptions, stateful behavior, and business-logic fault semantics (declines, insufficient funds, rate limits, disputes). Postman and WireMock target human-driven HTTP testing; they don't speak MCP and don't model business state.
- **Open & self-hostable.** `pip install`, runs locally, offline, Apache-2.0 — not a hosted SaaS.

## Install

```bash
pip install mockworld-mcp
```

Requires Python 3.11+. The distribution is named `mockworld-mcp`; the import package and CLI are simply `mockworld`.

## Quickstart

```bash
mockworld list                        # the built-in mocks
mockworld run mock:payments           # a stateful fake Stripe over stdio (MCP)
mockworld run mock:payments --transport http --port 8931   # Streamable HTTP + control plane
mockworld run mock:payments --seed 42 --faults hostile     # deterministic + adversarial
mockworld inspect mock:crm            # tools, faults, and state shape without running
mockworld demo mock:payments          # prove determinism: same seed → identical transcript
```

Point any MCP client (or a [stampede](https://github.com/swarmproof/stampede) swarm) at it. `mockworld reset --seed 42` returns a running server to a byte-identical world, every time.

## Use it in your tests

Installing mockworld gives every `pytest` run a `mockworld` fixture — a deterministic fake Stripe in two lines:

```python
def test_agent_handles_a_decline(mockworld):
    pay = mockworld.start("mock:payments", seed=7, faults="hostile")
    cust = pay.call("create_customer", {"name": "Ada", "balance": 10_000}).data
    result = my_agent.charge(pay, cust["id"], 2_500)   # your agent, against a fake Stripe
    assert result.retried_sanely
```

Seeded and in-memory: each test is deterministic and isolated, and 50 parallel workers don't collide.

## Built-in mocks

| Mock | Shape | What it exercises |
|------|-------|-------------------|
| `mock:payments` | Stripe | charges, refunds, idempotency; `refund ≤ captured`, balance conservation |
| `mock:crm` | Records | the delete-vs-archive **misuse map**; audit log; optimistic locking |
| `mock:exchange` | CEX | balances, orders, fills, **slippage**; balance conservation |
| `mock:email` | Gmail/SMTP | send/read/search; **sticky bounces**; threading; rate limits |
| `mock:files` | S3 | read-after-write consistency; versioning; slow-download latency |
| `mock:hello` | — | the smallest complete example, for learning the schema |

Each enforces stateful invariants and injects seeded, business-shaped faults. A declarative `mock.yaml` plus an optional Python handler defines a mock.

## Author & share mocks

```bash
mockworld new mystripe                # scaffold a runnable, clean-linting mock to grow from
mockworld validate ./mystripe         # schema, handler ABI, determinism smells, description quality
mockworld pack ./mystripe             # print a registry entry (checksum + metadata) to publish

mockworld search weather              # the public registry
mockworld add mock:weather            # install a community mock — checksum-verified + safety-gated
```

The registry ([swarmproof/mockworld-registry](https://github.com/swarmproof/mockworld-registry)) is an index-as-repo: contribute a mock by opening a PR with a folder and an index entry. See [`docs/AUTHORING.md`](./docs/AUTHORING.md) and [`mock:hello`](./src/mockworld/mocks/hello/).

## Compose, record, and simulate

```bash
# Compose several mocks into one world with a shared customer namespace:
mockworld run world:examples/worlds/ecommerce.yaml --seed 42
#   → payments + crm + email share the same 50 customers: charge → update CRM → email, consistently.

# Scaffold a runnable mock from an OpenAPI spec — or from captured traffic (HAR):
mockworld record --openapi ./petstore.yaml --out ./petstore_mock
mockworld record --har ./session.har --name orders --out ./orders_mock

# Run a scripted-persona swarm → an Agent Readiness Report (the misuse map):
mockworld swarm mock:crm --agents 200 --goal hide --seed 42
#   ⚠ 32.5% of agents destroyed data they meant to hide (delete vs archive) — reproducible.
mockworld swarm mock:crm --agents 200 --seed 42 --descriptions ambiguous
#   ⚠ 45.5% — same swarm, vaguer tool descriptions.

# Save a dirtied world as a portable artifact; reload it anywhere to reproduce a bug:
mockworld snapshot save mock:payments bug123.mw.json --seed 7

# Govern fidelity drift against a real provider's OpenAPI contract:
mockworld verify mock:payments --against ./stripe-openapi.yaml

# Export target-side traces (OTel GenAI profile) to any OTLP collector:
mockworld run mock:payments --otlp http://localhost:4318
```

The joint chaos demo — a transport interruption *and* a business decline at once, with the side-effect firing exactly once — runs standalone:

```bash
python examples/demos/exactly_once_under_chaos.py
```

## Project structure

```
mockworld/
├── src/mockworld/
│   ├── determinism.py       # the seeded entropy funnel (clock/ids/rng/fault-dice)
│   ├── state.py             # copy-on-write state store (memory / sqlite)
│   ├── session.py           # per-session isolation
│   ├── schema.py            # the mock.yaml pydantic models
│   ├── faults.py            # business-logic fault injector
│   ├── dispatch.py          # declarative CRUD + Python handler ABI
│   ├── engine.py            # the transport-free call path (start here)
│   ├── server.py            # MCP exposure: stdio + Streamable HTTP + resources
│   ├── control.py           # control plane + stampede Target protocol
│   ├── trace.py             # OTel-GenAI-profile spans + NDJSON + OTLP export
│   ├── registry.py          # add / search / pack (index-as-repo)
│   ├── world.py             # compose mocks with a shared identity namespace
│   ├── record.py            # scaffold a mock from OpenAPI / HAR
│   ├── snapshot.py          # portable scenario snapshots (+ migration)
│   ├── swarm.py             # persona swarm → Agent Readiness Report
│   ├── verify.py            # contract-drift check vs OpenAPI
│   ├── cli.py               # the mockworld command
│   └── mocks/               # payments · crm · exchange · email · files · hello
├── tests/                   # 86 tests mapping to the TEST-PLAN gates
├── docs/                    # ARCHITECTURE · PRD · AUTHORING · RELEASING · TEST-PLAN · …
├── examples/                # worlds/ · demos/ · registry/
└── .github/workflows/       # ci.yml · release.yml
```

The engine has no MCP dependency; `server.py`, `control.py`, and `cli.py` are adapters over it. This keeps the determinism and isolation tests dependency-free.

## Documentation

| Doc | What it covers |
|-----|----------------|
| [`docs/AUTHORING.md`](./docs/AUTHORING.md) | Write a mock: schema, handler ABI, faults, publishing |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | Engine design, session isolation, the stampede contract, ADRs |
| [`docs/PRD.md`](./docs/PRD.md) | Requirements (the REQ-IDs referenced across the docs) |
| [`docs/TEST-PLAN.md`](./docs/TEST-PLAN.md) | Test strategy, E2E scenarios, and CI gates |
| [`docs/RELEASING.md`](./docs/RELEASING.md) | How releases are cut and published to PyPI |
| [`CHANGELOG.md`](./CHANGELOG.md) | Release history |
| [`SPEC.md`](./SPEC.md) · [`ROADMAP.md`](./ROADMAP.md) | The original spec and roadmap |

## Contributing

Contributions welcome — bug reports, new mocks, and features. See [`CONTRIBUTING.md`](./CONTRIBUTING.md). Three rules: determinism is required (all entropy comes from the seeded `ctx`; the validator enforces it), faults are business-logic only, and every mock ships a `fidelity.md`.

```bash
git clone https://github.com/swarmproof/mockworld && cd mockworld
uv venv && uv pip install -e ".[dev]"
python -m pytest -q
```

## License

[Apache-2.0](./LICENSE). Citable via [`CITATION.cff`](./CITATION.cff).

## Part of the Swarm Proof toolkit

mockworld is one of the Swarm Proof projects for building and testing reliable agents:

| Project | What it does |
|---------|--------------|
| [stampede](https://github.com/swarmproof/stampede) | Point a herd of realistic agents at your system before real ones arrive |
| **mockworld** ← *you are here* | A synthetic internet for agents — fake Stripe, Gmail, exchange, instantly |
| [mcp-probe](https://github.com/swarmproof/mcp-probe) | The CI quality suite for MCP servers — lint, contract-test, benchmark, load |
| [costbomb](https://github.com/swarmproof/costbomb) | Denial-of-wallet fuzzing — find the inputs that make your agent spend $500 |
| [exactly-once](https://github.com/swarmproof/exactly-once) | Idempotency middleware so agent side-effects fire once |
| [agent-postmortems](https://github.com/swarmproof/agent-postmortems) | A structured incident database + post-mortem standard for agent failures |
| [awesome-agent-reliability](https://github.com/swarmproof/awesome-agent-reliability) | The curated map of the field |
