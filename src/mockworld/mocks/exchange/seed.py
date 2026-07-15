"""Deterministic base dataset for mock:exchange (REQ-STATE-2).

Pure function of the seed: same seed → identical markets, accounts, balances, and
historical orders, so a fixed account/symbol resolves to the same book on every
run (the anchor for the hero E2E and for reproducible slippage rejections).

Prices and quote (USD) balances are in minor units (cents); base-asset sizes are
whole units.
"""

from __future__ import annotations

# (symbol, base, quote, price_in_cents, halted)
_MARKETS = [
    ("BTC-USD", "BTC", "USD", 6_000_000, False),   # $60,000.00
    ("ETH-USD", "ETH", "USD", 300_000, False),     # $3,000.00
    ("SOL-USD", "SOL", "USD", 15_000, False),      # $150.00
    ("AAPL-USD", "AAPL", "USD", 18_000, False),    # $180.00
    ("TSLA-USD", "TSLA", "USD", 25_000, False),    # $250.00
    ("DOGE-USD", "DOGE", "USD", 12, True),         # $0.12, trading halted
]

_STATUSES = ["filled", "filled", "partially_filled", "open", "rejected", "cancelled"]


def generate(ctx, definition) -> dict:
    volume = definition.seed.volume

    markets: dict[str, dict] = {}
    for symbol, base, quote, price, halted in _MARKETS:
        markets[symbol] = {
            "symbol": symbol,
            "base": base,
            "quote": quote,
            "price": price,
            "halted": halted,
        }

    accounts: dict[str, dict] = {}
    balances: dict[str, dict] = {}
    for _ in range(volume.get("accounts", 0)):
        aid = ctx.ids.next("acct")
        accounts[aid] = {"id": aid, "name": ctx.fake.name()}

        # Every account holds quote (USD) cash, plus some base-asset positions.
        usd_key = f"{aid}:USD"
        balances[usd_key] = {
            "id": usd_key,
            "account_id": aid,
            "asset": "USD",
            "amount": ctx.fake.amount_cents(100_000_00, 1_000_000_00),  # $100k–$1M
        }
        for _symbol, base, _quote, _price, _halted in _MARKETS:
            if base == "USD":
                continue
            units = ctx.rng.randint(0, 20)
            if units:
                bkey = f"{aid}:{base}"
                balances[bkey] = {
                    "id": bkey,
                    "account_id": aid,
                    "asset": base,
                    "amount": units,
                }

    account_ids = list(accounts)
    symbols = list(markets)
    price_of = {s: m["price"] for s, m in markets.items()}

    orders: dict[str, dict] = {}
    base_ts = 1_700_000_000
    for i in range(volume.get("orders", 0)):
        oid = ctx.ids.next("ord")
        aid = ctx.rng.choice(account_ids) if account_ids else None
        symbol = ctx.rng.choice(symbols)
        side = ctx.rng.choice(["buy", "sell"])
        size = ctx.rng.randint(1, 10)
        status = ctx.rng.choice(_STATUSES)
        price = price_of[symbol]

        if status == "filled":
            filled, fill_price = size, price
        elif status == "partially_filled":
            filled, fill_price = max(1, size // 2), price
        else:  # open / rejected / cancelled — nothing filled
            filled, fill_price = 0, None

        limit_price = price if ctx.rng.random() < 0.5 else None
        orders[oid] = {
            "id": oid,
            "account_id": aid,
            "symbol": symbol,
            "side": side,
            "size": size,
            "limit_price": limit_price,
            "status": status,
            "filled": filled,
            "fill_price": fill_price,
            "created": base_ts + i,
        }

    return {
        "markets": markets,
        "accounts": accounts,
        "balances": balances,
        "orders": orders,
    }
