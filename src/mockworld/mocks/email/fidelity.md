# mock:email — fidelity notes

A Gmail/SMTP-shaped email service. Deterministic and LLM-free: every id,
timestamp, and fault decision derives from the run seed.

**Fidelity: partial.** We model the behaviors an agent must get right — sending,
threading, listing, searching, and the three ways a send realistically fails
(permanent bounce, spam rejection, rate limit) — not the full Gmail API surface
(labels, attachments, MIME, drafts, IMAP flags, quotas, push).

## State

| Collection          | Key       | Notes                                                    |
|---------------------|-----------|----------------------------------------------------------|
| `messages`          | `id`      | `folder` ∈ {sent, inbox}; `status` ∈ {sent, bounced, rejected}. Sends land in `sent`. |
| `bounced_addresses` | `address` | Permanently-dead recipients. Seeded, immutable base.     |

The mailbox owner is `me@mockworld.local`. Seed volume: `messages: 24` plus a
fixed set of 3 bounced addresses.

## Tools

- `send_email(to, subject, body, thread_id?, from?)` — persists a message to the
  `sent` folder and returns it. Threading: with `thread_id` the message joins
  that conversation; without one a fresh `thread_<...>` id is minted and
  returned. Sending to a bounced address fails `hard_bounce`.
- `list_messages(folder?)` — `{data, count}`, key-sorted stable order; optional
  `folder` filter.
- `get_message(message_id)` — one message, or `not_found`.
- `search(query)` — case-insensitive substring over `subject` + `body` + `to`.

## Invariants (tested)

1. **sent persists** — `send_email` returning success commits state, so the
   message is retrievable via `get_message`/`list_messages` afterward. (The
   engine commits only on a successful result.)
2. **bounces are sticky** — an address in `bounced_addresses` hard-bounces on
   every send, on every retry. That collection is seeded into the immutable base
   layer, so the sticky signal is durable regardless of any call's outcome.
3. **threading** — messages sharing a `thread_id` group together; a send without
   a `thread_id` gets a fresh one, so a reply stays in-thread and a new send
   starts its own.

## Faults (declared per tool on `send_email`)

| Fault           | Trigger                                                   | Shape                       |
|-----------------|-----------------------------------------------------------|-----------------------------|
| `hard_bounce`   | conditional (`when:` recipient ∈ `bounced_addresses`) **and** probabilistic `0.05` | 400, `error_response`       |
| `rate_limited`  | probabilistic `0.1`, `retry_after_s: 3`                   | 429 + `retry_after`         |
| `spam_rejected` | probabilistic `0.05`                                       | 400, `error_response`       |
| `latency`       | distribution `{p50_ms: 60, p99_ms: 900}`                  | metadata only               |

Profiles: `none` (no faults), `realistic` (`inherit: tool_defaults`), `hostile`
(inherit + `send_email` overrides: `rate_limited 0.4`, `hard_bounce 0.2`,
`spam_rejected 0.2`).

### E2E-5: rate-limit visibility

Under `realistic`, an agent sending emails in a tight loop hits `rate_limited`
(429) at seed-deterministic call indices (the fault die is keyed on
`(tool, call-index, rule)`). A well-behaved agent honors `retry_after`; a naive
retry storm re-sends immediately and is plainly visible in the trace.

## Design note: stickiness vs. short-circuit faults

A declared fault (`error_response`, `rate_limited`, …) **short-circuits before
the handler** and, being an error, is rolled back by the engine — faults never
mutate state (REQ-STATE-3). Two consequences shaped this design:

- **Sticky bounces are seeded, not written at runtime.** Because a short-circuit
  bounce skips the handler and an error result rolls back any write, we cannot
  "learn" a new bad address into `bounced_addresses` mid-call and have it persist.
  Instead the known-dead addresses live in the seeded base, and both the
  `when:` fault condition and the handler's membership check read them — so those
  addresses bounce **every** time (demonstrably sticky), including under the
  `none` profile where no faults fire and the handler is the sole authority.
- **A probabilistic bounce is a one-shot.** A new address that trips the `0.05`
  `hard_bounce` die bounces for that call only; it does not become permanently
  sticky (it is never added to the seeded set). This is intentional: permanent
  stickiness is reserved for the seeded dead addresses, which is what the sticky
  invariant is asserted against.
- **A bounced send leaves no `messages` row.** Since the send returns an error,
  the engine rolls back the call's writes; the durable evidence of a permanent
  bounce is the `bounced_addresses` entry, not a `status: bounced` message. The
  bounce surfaces to the agent as a first-class `hard_bounce` error (400), which
  is the signal an agent-reliability harness cares about.
