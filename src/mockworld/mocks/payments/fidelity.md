# fidelity — mock:payments

**Fidelity level:** `partial` — Stripe-shaped and realistic enough to break agents
correctly, not a vendor-exact clone of the Stripe API.

## What this mock models
- Customers with a spendable `balance` (cents) and charges against them.
- Charge lifecycle: `requires_capture` → `succeeded` → `refunded`.
- **Idempotency**: a `create_charge` retried with the same `idempotency_key`
  replays the original charge instead of double-charging.
- **Invariants** (enforced in handlers):
  - `balance ≥ 0` — a capture cannot exceed the customer's balance.
  - `refund ≤ captured` — refunds never exceed the remaining captured amount;
    a fully-refunded charge rejects further refunds.
  - **Money conservation** — a refund credits the customer's balance back.
- Stripe-shaped error bodies (`{type, code, decline_code, message}`).

## Faults
| Fault | Trigger | Notes |
|-------|---------|-------|
| `card_declined` | probabilistic (5% realistic / 30% hostile) | seed-deterministic step |
| `insufficient_funds` | conditional — `amount > customer.balance` | stateful, not a dice roll |
| `rate_limited` | probabilistic (2% / 15% hostile) | 429 + `retry_after` |
| `latency` | distribution p50 80ms / p99 1200ms | recorded in trace, not slept by default |
| `partial_outage` | `get_charge` forced down under `hostile` | the "created but can't read it" double-charge trap |

## What this mock does NOT model
- Payment methods, 3-D Secure, SCA, webhooks, or Connect/marketplaces.
- Multi-currency conversion (currency is stored, not converted).
- Payouts, fees, tax, or Radar fraud scoring beyond the `dispute` flag.
- The full Stripe object surface (Invoices, Subscriptions, PaymentIntents state
  machine) — charges are modeled directly.
