# Changelog

All notable changes to mockworld are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow SemVer.

## [Unreleased]

### Added
- **OTLP trace export** (REQ-OBS-3): `mockworld run --otlp <collector-url>` POSTs
  target-side spans as OTLP/HTTP JSON to `<url>/v1/traces` — dependency-free, so
  mockworld traces drop into any OpenTelemetry backend. Best-effort and
  self-disabling if the collector is down.
- **MCP resources** (REQ-MCP-4): each server exposes read-only reference data —
  `mockworld://mock` (tools + state shape + fidelity), `mockworld://faults`
  (declared fault catalog + profiles), and `mockworld://state/<collection>`
  (the session's current data).

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
