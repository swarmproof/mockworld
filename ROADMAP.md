# mockworld — Roadmap

## v0.1
- Shared engine + 5 built-in mocks (payments, email, exchange, crm, files)
- One-command run; reset/seed for determinism; fault injection
- Ships alongside stampede's first finance demos

## v0.2 ✅ (implemented)
- ✅ Registry + `mockworld add`/`search`/`pack` — index-as-repo, checksum + safety gate
- ✅ Record-mode — scaffold a runnable mock from an OpenAPI spec
- ✅ Mock composition — a "world" = several mocks with a shared identity namespace

## v0.3
- Deep stampede integration (target a `mockworld` world directly)
- Scenario snapshots (shareable seeded world state for reproducible bug reports)
