# mockworld — Roadmap

## v0.1
- Shared engine + 5 built-in mocks (payments, email, exchange, crm, files)
- One-command run; reset/seed for determinism; fault injection
- Ships alongside stampede's first finance demos

## v0.2
- Registry + `mockworld add`
- Record-mode (capture a real API's shapes to scaffold a mock)
- Mock composition (a "world" = several mocks with shared state)

## v0.3
- Deep stampede integration (target a `mockworld` world directly)
- Scenario snapshots (shareable seeded world state for reproducible bug reports)
