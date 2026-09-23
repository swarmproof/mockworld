# mockworld — Roadmap

Released on PyPI as [`mockworld-mcp`](https://pypi.org/project/mockworld-mcp/).
See [`CHANGELOG.md`](./CHANGELOG.md) for versions and the full history.

## v0.1 ✅ — engine + built-in mocks

- ✅ Deterministic, LLM-free engine: one-command run, reset/seed, fault injection, per-session isolation
- ✅ Built-in mocks: `payments`, `crm`, `exchange`, `email`, `files` (+ `hello` example)
- ✅ MCP over stdio and Streamable HTTP; out-of-band control plane

## v0.2 ✅ — the moat

- ✅ Registry + `mockworld add`/`search`/`pack` — index-as-repo, checksum + safety gate. Public
  registry live at [swarmproof/mockworld-registry](https://github.com/swarmproof/mockworld-registry)
  (`weather`, `slack`, `twilio`, `github`, `calendar`)
- ✅ Record-mode — scaffold a runnable mock from an OpenAPI spec **or** a HAR capture
- ✅ Mock composition — a "world" = several mocks with a shared identity namespace

## v0.3 ✅ — the ecosystem

- ✅ stampede `Target` protocol + a deterministic swarm harness → an Agent Readiness Report (misuse map)
- ✅ Scenario snapshots — portable `.mw.json` artifacts (seed + versions + state) with cross-version migration
- ✅ Contract-verify — `mockworld verify --against <openapi>` for fidelity-drift governance

## Shipped beyond the original roadmap

- ✅ Runtime sandbox for untrusted registry handlers (hardened subprocess isolation)
- ✅ OTLP trace export; read-only `mockworld://` MCP resources; ambiguous-description variants
- ✅ `mockworld` pytest fixture; `mockworld new` authoring scaffold; automated PyPI release pipeline

## Open (needs the sibling projects)

- **Deep stampede integration** — `stampede.yaml`-driven runs against a mockworld world, and the joint
  launch demo. stampede now ships a `TargetAdapter` ABC and hand-coded `crm`/`payments` worlds; a
  mockworld-backed target would replace those with the whole mock library. Unblocked as of stampede's
  public release.
- **Shared trace package** — swap mockworld's trace shim for the shared
  `agent_reliability_core.trace` schema (the `swarmproof.*` attribute registry stampede publishes).
