# Simulate the users and the world

*A joint write-up for [stampede](https://github.com/swarmproof/stampede) and
[mockworld](https://github.com/swarmproof/mockworld).*

You can't test an agent that takes real-world actions the way you test a function.
An agent charges cards, sends email, deletes records, places trades — and to know
whether it does those things *correctly under pressure*, you need two things you
usually don't have at once: a realistic population of agents hitting your system,
and a realistic world for them to act on. Point a half-finished agent at real
Stripe and you leak money; point it at nothing and you find the failures in
production.

stampede and mockworld are the two halves. **stampede simulates the users** — a
seeded swarm of agents with different temperaments and goals. **mockworld
simulates the world** — deterministic, LLM-free fake services (a fake Stripe,
Gmail, exchange, CRM, GitHub, Slack, …) as MCP servers. Each is useful alone.
Together they're a complete test harness: a herd of realistic agents acting on a
realistic world, reproducibly, offline, for free.

## Two commands

```bash
pip install "stampede[mockworld]"
stampede run --dry-run -c examples/mockworld_crm.yaml
```

That's a 50-agent swarm against a fake CRM, no keys and no network, producing an
Agent Readiness Report — including the misuse map:

```
 goal expected     agents called      confusion       n
 archive_record    delete_record      ███░░░░░ 38%     8
```

38% of agents that were told to *hide* a record called `delete_record` — permanent
destruction — instead of `archive_record`. Naive personas did it 50% of the time.
The record is genuinely gone in the mock's state, and mockworld's audit log
attributes each choice, so the number is measured, not asserted.

## The demo we couldn't build before

The interesting agent failures happen when two kinds of trouble hit at once: the
network flakes *and* the business logic says no. stampede owns transport chaos
(killing an agent mid-call, timeouts); mockworld owns business faults (a declined
card, a 429, insufficient funds). Compose them and ask the question that actually
matters:

```bash
stampede run --dry-run -c examples/mockworld_payments.yaml
```
```
chaos: agent_kill=8, timeout=38 · exactly-once holds
0 exactly-once violations
```

stampede killed 8 agents mid-charge and timed out 38 more while mockworld threw
declines and rate-limits — and the charge still fired **exactly once**, because
the agents passed an idempotency key and mockworld deduped the retry. That single
line is the recovery guarantee proven across both fault layers at the same time.

## Why deterministic

Everything above runs from a seed. `--seed 42` produces the same swarm, the same
declines at the same steps, and the same report — on your laptop, in CI, across 50
parallel workers. That is the deliberate bet: the 2026 crop of agent sandboxes put
an LLM in the response path, which is convenient and never behaves the same way
twice. A stochastic harness can't give you a CI run that's green for the same
reason twice or a bug you can hand to a teammate and have them reproduce byte for
byte. mockworld has no LLM in the hot path, and stampede's dry-run pipeline is
zero-LLM by construction.

## Run it yourself

```bash
pip install "stampede[mockworld]"

# the misuse map
stampede run --dry-run -c examples/mockworld_crm.yaml

# transport chaos + business faults + exactly-once
stampede run --dry-run -c examples/mockworld_payments.yaml

# or point a swarm at any mock in the public registry
pip install mockworld-mcp
mockworld add mock:github          # or slack, twilio, calendar, weather
```

Both reports land at `./stampede-report.html`. Drop `--dry-run` and add a model
(`ollama:llama3.1`, `anthropic:claude-haiku`) for a live swarm.

## Links

- mockworld — https://github.com/swarmproof/mockworld · `pip install mockworld-mcp`
- stampede — https://github.com/swarmproof/stampede
- the mock registry — https://github.com/swarmproof/mockworld-registry

---

### Channels (draft copy)

**Show HN:** *Show HN: Simulate a swarm of agents against a fake Stripe — and prove
exactly-once under chaos*

**r/mcp:** A deterministic, LLM-free set of fake services (Stripe/Gmail/CRM/GitHub/…)
as MCP servers, plus an agent-swarm simulator that drives them. One command, offline,
seeded. Misuse map + exactly-once-under-chaos in the post.

**X thread (outline):**
1. You can't point a half-built agent at real Stripe. So how do you test one that
   moves money? You fake the world *and* the users — deterministically.
2. `pip install "stampede[mockworld]"` → a 50-agent swarm against a fake CRM. 38%
   deleted a record they were told to archive. [misuse-map image]
3. The real test: kill agents mid-charge, throw declines and 429s at the same time.
   Did the charge fire once? `exactly-once holds`. [payments-run image]
4. All of it from a seed — same declines, same report, in CI, across 50 workers. No
   LLM in the response path. That's the whole point.
5. Open source, Apache-2.0. Links 👇
