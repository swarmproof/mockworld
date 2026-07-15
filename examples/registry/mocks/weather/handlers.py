"""weather handlers — a minimal community-mock example (all entropy via ctx)."""

from __future__ import annotations

from mockworld import Result


def get_forecast(ctx, params) -> Result:
    station = ctx.state.stations.get(params["id"])
    if station is None:
        return Result.error("not_found", f"No such station: {params['id']}")
    base = station["temp_c"]
    days = [base + ctx.rng.randint(-4, 4) for _ in range(3)]
    return Result.ok({"id": station["id"], "city": station["city"], "forecast_c": days})
