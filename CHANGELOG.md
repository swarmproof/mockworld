# Changelog

All notable changes to mockworld are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow SemVer.

## [0.2.2] — 2026-09-04

### Changed
- Rewrote the README to open-source standard: badges (PyPI/CI/Python/license), a
  table of contents, a built-in-mocks table, a project-structure map, and a
  documentation index. No code changes — refreshes the PyPI project page.

## [0.2.1] — 2026-09-02

### Added
- Registry **`github:` source scheme** (`owner/repo@ref/subdir`): `mockworld add`
  can install a mock that lives in a subdirectory of a shared index-as-repo, so
  the public `mockworld-registry` grows by simple PRs (a folder + an index entry),
  no per-mock release asset. Powers `mockworld add mock:<name>` against the
  default public registry.

## [0.2.0] — 2026-09-02

Distribution renamed to **`mockworld-mcp`** on PyPI (`import mockworld` and the
`mockworld` CLI are unchanged) — the plain name is reserved by an unrelated project.

### Added
- **OTLP trace export** (REQ-OBS-3): `mockworld run --otlp <collector-url>` POSTs
  target-side spans as OTLP/HTTP JSON to `<url>/v1/traces` — dependency-free, so
  mockworld traces drop into any OpenTelemetry backend. Best-effort and
  self-disabling if the collector is down.
- **MCP resources** (REQ-MCP-4): each server exposes read-only reference data —
  `mockworld://mock` (tools + state shape + fidelity), `mockworld://faults`
  (declared fault catalog + profiles), and `mockworld://state/<collection>`
  (the session's current data).
- **Ambiguous tool-description variants** (REQ-MCP-6): a tool can declare an
  `ambiguous_description`; `--descriptions ambiguous` serves it. The swarm is
  clarity-sensitive, so the misuse map can A/B description quality — e.g.
  crm delete-vs-archive misuse rises from ~33% (clear) to ~46% (ambiguous),
  reproducibly.

## [0.1.0] — 2026-09-01

First public release — the deterministic, LLM-free MCP mock engine plus the full
v0.1–v0.4 feature surface.

### Engine
- Seeded `DeterministicContext` (clock/ids/rng/fault-dice on independent
  substreams); byte-identical replay across runs, hosts, and both state stores.
- Copy-on-write per-session isolation keyed on `Mcp-Session-Id` (50+ parallel
  sessions, zero cross-talk).
- Declarative `mock.yaml` schema + Python handler ABI; Memory and SQLite stores.
- Business-logic fault injector: probabilistic + conditional (`when:`) faults,
  profiles (`none`/`realistic`/`hostile`), realistic vendor-shaped error bodies.
- Target-side trace emission as an OpenTelemetry GenAI profile.

### Surface
- MCP over stdio and Streamable HTTP; out-of-band control plane; stampede
  `Target` protocol.
- CLI: `run`, `list`, `inspect`, `validate`, `reset`, `demo`, `new`, `add`,
  `search`, `pack`, `record`, `swarm`, `verify`, `snapshot`.

### Built-in mocks
- `payments` (Stripe-shaped), `crm` (delete-vs-archive misuse map), `exchange`,
  `email`, `files`, and `hello` (the authoring example).

### Ecosystem
- Registry (`add`/`search`/`pack`) with checksum + safety gate.
- World composition with a shared identity namespace.
- Record-mode: scaffold a mock from an OpenAPI spec **or** a HAR capture.
- Scenario snapshots (portable `.mw.json` + migration).
- Swarm harness → Agent Readiness Report (the misuse map).
- Contract-verify against an OpenAPI for fidelity-drift governance.

### Developer experience
- A `mockworld` pytest fixture (via the `pytest11` entry point).
- `mockworld new` scaffold and `docs/AUTHORING.md`.

### Fixed
- Wheel build no longer double-includes built-in mock data (removed a redundant
  `force-include`); `pip install mockworld` now ships the mocks correctly.
