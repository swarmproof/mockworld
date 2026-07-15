"""exchange handlers — the stateful invariants a fake CEX must enforce.

  * balance conservation: a fill debits one asset and credits the other using the
    fill price exactly (buy → -quote / +base, sell → -base / +quote). No balance
    ever goes negative; the account can only trade what it can pay for.
  * order → fill lifecycle: orders resolve to 'filled', 'partially_filled', or rest
    'open' (limit not yet marketable); a fill beyond tolerance is rejected outright.
  * slippage: every fill draws a deterministic price perturbation from `ctx.rng`;
    if the fill drifts past the allowed tolerance the order is rejected with
    `slippage_exceeded` and no balance moves.

All entropy comes from `ctx` (clock/ids/rng); importing time/random/uuid here
would be flagged by `mockworld validate`.
"""

from __future__ import annotations

from mockworld import Result

# Slippage model, expressed in basis points (1 bp = 0.01%).
MAX_SLIPPAGE_BPS = 120       # widest perturbation a single fill can draw
SLIPPAGE_TOLERANCE_BPS = 100  # drift past this rejects the order (INV-3)
_BPS = 10_000


def _bal_key(account_id: str, asset: str) -> str:
    return f"{account_id}:{asset}"


def _get_amount(ctx, account_id: str, asset: str) -> int:
    row = ctx.state.balances.get(_bal_key(account_id, asset))
    return row["amount"] if row else 0


def _set_amount(ctx, account_id: str, asset: str, amount: int) -> None:
    key = _bal_key(account_id, asset)
    row = ctx.state.balances.get(key)
    if row is None:
        row = {"id": key, "account_id": account_id, "asset": asset, "amount": 0}
    row["amount"] = amount
    ctx.state.balances.put(key, row)


def _record_order(ctx, account_id, symbol, side, size, limit_price, status, filled, fill_price):
    order = {
        "id": ctx.ids.next("ord"),
        "account_id": account_id,
        "symbol": symbol,
        "side": side,
        "size": size,
        "limit_price": limit_price,
        "status": status,
        "filled": filled,
        "fill_price": fill_price if filled else None,
        "created": ctx.now(),
    }
    ctx.state.orders.put(order["id"], order)
    return order


def get_ticker(ctx, params) -> Result:
    symbol = params["symbol"]
    market = ctx.state.markets.get(symbol)
    if market is None:
        return Result.error("not_found", f"No such market: {symbol}")
    return Result.ok(
        {
            "symbol": market["symbol"],
            "base": market["base"],
            "quote": market["quote"],
            "price": market["price"],
            "halted": market["halted"],
        }
    )


def get_balances(ctx, params) -> Result:
    account_id = params["account_id"]
    if not ctx.state.accounts.exists(account_id):
        return Result.error("not_found", f"No such account: {account_id}")
    rows = ctx.state.balances.filter(account_id=account_id)
    return Result.ok({"account_id": account_id, "balances": rows})


def place_order(ctx, params) -> Result:
    account_id = params["account_id"]
    symbol = params["symbol"]
    side = params["side"]
    size = params["size"]
    limit_price = params.get("limit_price")

    if side not in ("buy", "sell"):
        return Result.error("invalid_request", "side must be 'buy' or 'sell'")
    if size <= 0:
        return Result.error("invalid_request", "size must be a positive integer")

    if not ctx.state.accounts.exists(account_id):
        return Result.error("not_found", f"No such account: {account_id}")

    market = ctx.state.markets.get(symbol)
    if market is None:
        return Result.error("not_found", f"No such market: {symbol}")
    if market["halted"]:
        return Result.error("market_halted")

    base = market["base"]
    quote = market["quote"]
    mkt_price = market["price"]

    # Deterministic slippage: draw a signed perturbation from the seeded per-call RNG.
    slip_bps = ctx.rng.randint(-MAX_SLIPPAGE_BPS, MAX_SLIPPAGE_BPS)
    fill_price = max(1, round(mkt_price * (_BPS + slip_bps) / _BPS))

    # Slippage guard (INV-3): a fill that drifted past tolerance is rejected; because
    # this returns an error the engine rolls back — no partial writes, conservation holds.
    drift_bps = abs(fill_price - mkt_price) * _BPS // mkt_price if mkt_price else 0
    if drift_bps > SLIPPAGE_TOLERANCE_BPS:
        return Result.error(
            "slippage_exceeded",
            f"Fill price {fill_price} drifted {drift_bps} bps from market {mkt_price} "
            f"(tolerance {SLIPPAGE_TOLERANCE_BPS} bps); order rejected.",
        )

    # A limit order that isn't marketable at the fill price rests as 'open' (no fill).
    if limit_price is not None:
        not_marketable = (
            (side == "buy" and fill_price > limit_price)
            or (side == "sell" and fill_price < limit_price)
        )
        if not_marketable:
            order = _record_order(
                ctx, account_id, symbol, side, size, limit_price, "open", 0, fill_price
            )
            return Result.ok(order)

    if side == "buy":
        quote_bal = _get_amount(ctx, account_id, quote)
        affordable = quote_bal // fill_price
        if affordable <= 0:
            return Result.error(
                "insufficient_funds",
                f"Balance {quote_bal} {quote} cannot buy 1 {base} at {fill_price}.",
            )
        fill_size = min(size, affordable)
        cost = fill_size * fill_price
        _set_amount(ctx, account_id, quote, quote_bal - cost)  # debit quote
        _set_amount(ctx, account_id, base, _get_amount(ctx, account_id, base) + fill_size)  # credit base
    else:  # sell
        base_bal = _get_amount(ctx, account_id, base)
        if base_bal <= 0:
            return Result.error(
                "insufficient_funds", f"No {base} available to sell (balance {base_bal})."
            )
        fill_size = min(size, base_bal)
        proceeds = fill_size * fill_price
        _set_amount(ctx, account_id, base, base_bal - fill_size)  # debit base
        _set_amount(ctx, account_id, quote, _get_amount(ctx, account_id, quote) + proceeds)  # credit quote

    status = "filled" if fill_size == size else "partially_filled"
    order = _record_order(
        ctx, account_id, symbol, side, size, limit_price, status, fill_size, fill_price
    )
    return Result.ok(order)


def cancel_order(ctx, params) -> Result:
    order_id = params["order_id"]
    order = ctx.state.orders.get(order_id)
    if order is None:
        return Result.error("not_found", f"No such order: {order_id}")
    if order["status"] not in ("open", "partially_filled"):
        return Result.error(
            "invalid_request",
            f"Order {order_id} is {order['status']} and cannot be cancelled.",
        )
    order["status"] = "cancelled"
    ctx.state.orders.put(order_id, order)
    return Result.ok(order)


def get_order(ctx, params) -> Result:
    order = ctx.state.orders.get(params["order_id"])
    if order is None:
        return Result.error("not_found", f"No such order: {params['order_id']}")
    return Result.ok(order)
