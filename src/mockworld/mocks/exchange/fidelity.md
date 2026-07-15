# fidelity — mock:exchange

**Fidelity level:** `partial` — CEX-shaped (Binance/Coinbase-style) and realistic
enough to break agents correctly, not a vendor-exact clone of any exchange API.

## What this mock models
- **Markets** for a trading pair (`BTC-USD`, `AAPL-USD`, …) with a last `price`,
  `base`/`quote` assets, and a `halted` flag. Prices are in minor units (cents).
- **Per-asset balances** keyed `"{account_id}:{asset}"`. Quote balances (USD) are
  in cents; base-asset balances (BTC, ETH, …) are whole units.
- **Order lifecycle**: `open` (limit resting, not yet marketable) → `filled` /
  `partially_filled`; also `rejected` and `cancelled`. `cancel_order` only acts on
  `open`/`partially_filled` orders.
- Market orders (no `limit_price`) fill immediately at market ± slippage; limit
  orders fill only when marketable and otherwise rest `open`.
- **Invariants** (enforced in handlers):
  - **Balance conservation** — a buy debits exactly `fill_size × fill_price` from
    the quote asset and credits `fill_size` of the base asset; a sell is the
    reverse. Nothing is created or destroyed by the accounting.
  - **No negative balance** — an account can only fill what it can pay for; an
    unaffordable buy is capped to a partial fill or rejected `insufficient_funds`.
  - **Slippage tolerance** — every fill draws a deterministic price perturbation
    from `ctx.rng` (±120 bps); a fill drifting past ±100 bps is rejected with
    `slippage_exceeded` and no balance moves.

## Faults
| Fault | Trigger | Notes |
|-------|---------|-------|
| `slippage_exceeded` | probabilistic (5% realistic / 60% hostile) on `place_order` | seed-deterministic; also enforced in the handler via the tolerance check |
| `market_halted` | conditional — `state.markets[symbol].halted` | 503; also guarded in the handler |
| `insufficient_funds` | handler — quote balance can't cover even 1 unit (buy) or no base to sell | stateful, not a dice roll |
| `rate_limited` | probabilistic (20%) on `place_order` under `hostile` | 429 + `retry_after` |
| `latency` | distribution p50 40ms / p99 900ms | recorded in trace, not slept by default |

## What this mock does NOT model
- A real matching engine / order book depth — fills are against a single market
  price, not resting counter-orders. There is no counterparty account.
- Fees, funding rates, leverage/margin, or short selling.
- Market-price movement over time (price is static per seed), stop/OCO orders,
  or time-in-force beyond immediate-or-rest.
- Deposits/withdrawals, multi-venue routing, or fiat on/off ramps.

## The E2E target (E2E-7)
`place_order` with slippage armed → the fill price differs beyond tolerance and
the order is rejected (`slippage_exceeded`) or partially filled, while balance
conservation holds. Because a rejected order returns an error, the engine rolls
the call back: no partial writes, and total holdings are unchanged.
