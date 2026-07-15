# fidelity — mock:weather (example community mock)

**Fidelity level:** `sketch` — a teaching example for authoring + registry
install, not a serious weather API.

## Models
- Weather stations with a city, current temperature (°C), and condition.
- A deterministic 3-day forecast derived from the station's current temp.

## Faults
- `rate_limited` (5%) on `get_forecast`.

## Does NOT model
- Real geography, time-of-day, seasonality, or any external data source.
