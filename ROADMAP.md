# mockworld — Roadmap

## v0.1
- Shared engine + 5 built-in mocks (payments, email, exchange, crm, files)
- One-command run; reset/seed for determinism; fault injection
- Ships alongside stampede's first finance demos

## v0.2 ✅ (implemented)
- ✅ Registry + `mockworld add`/`search`/`pack` — index-as-repo, checksum + safety gate
- ✅ Record-mode — scaffold a runnable mock from an OpenAPI spec
- ✅ Mock composition — a "world" = several mocks with a shared identity namespace

## v0.3 ✅ (implemented)
- ✅ stampede `Target` protocol + a deterministic swarm harness producing an Agent Readiness Report (misuse map)
- ✅ Scenario snapshots — portable `.mw.json` artifacts (seed + versions + state) with cross-version migration
- ✅ Contract-verify — `mockworld verify --against <openapi>` for fidelity-drift governance
