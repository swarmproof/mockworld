"""Deterministic base dataset for the example weather mock."""

from __future__ import annotations

_CITIES = ["Reykjavik", "Nairobi", "Oslo", "Lima", "Cairo", "Tokyo", "Perth", "Quito"]
_CONDITIONS = ["clear", "cloudy", "rain", "snow", "fog", "windy"]


def generate(ctx, definition) -> dict:
    n = definition.seed.volume.get("stations", 0)
    stations: dict[str, dict] = {}
    for _ in range(n):
        sid = ctx.ids.next("wx")
        stations[sid] = {
            "id": sid,
            "city": ctx.rng.choice(_CITIES),
            "temp_c": ctx.rng.randint(-20, 40),
            "condition": ctx.rng.choice(_CONDITIONS),
        }
    return {"stations": stations}
