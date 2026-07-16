"""Scenario snapshots — portable, shareable world state (ROADMAP v0.3; REQ-SNAP-*).

A snapshot is a self-describing ``.mw.json`` artifact embedding the seed, mock
name + version, and the full session state. Load it on another machine and the
exact world (and the failing transcript that produced it) reconstructs — the
reproducible-bug-report story (E2E-9).

Across mock versions, a snapshot is migrated on load via an optional
``migrate_state(state, from_version, to_version)`` in the mock's handlers module
(REQ-DEF-8), so old snapshots stay loadable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import STDIO_SESSION, Engine

SNAPSHOT_VERSION = "1"


class SnapshotError(Exception):
    pass


def save(engine: Engine, path: str, *, session_id: str = STDIO_SESSION, created: int = 0) -> str:
    artifact = {
        "snapshot_version": SNAPSHOT_VERSION,
        "mock": engine.definition.name,
        "mock_version": engine.definition.version,
        "seed": engine.seed,
        "created": created,  # caller-supplied; the library never reads the wall clock
        "state": engine.store.snapshot_dict(session_id),
    }
    Path(path).write_text(json.dumps(artifact, indent=2, default=str))
    return path


def read_meta(path: str) -> dict[str, Any]:
    art = json.loads(Path(path).read_text())
    return {k: art[k] for k in ("snapshot_version", "mock", "mock_version", "seed", "created")}


def load(engine: Engine, path: str, *, session_id: str = STDIO_SESSION) -> dict[str, Any]:
    art = json.loads(Path(path).read_text())
    if art.get("snapshot_version") != SNAPSHOT_VERSION:
        raise SnapshotError(f"unsupported snapshot_version {art.get('snapshot_version')!r}")
    if art.get("mock") != engine.definition.name:
        raise SnapshotError(
            f"snapshot is for mock {art.get('mock')!r}, not {engine.definition.name!r}"
        )

    state = art["state"]
    from_v = art.get("mock_version")
    to_v = engine.definition.version
    if from_v != to_v:
        state = _migrate(engine, state, from_v, to_v)

    engine.sessions.get(session_id)  # ensure the session is tracked
    engine.store.install_overlay(session_id, state)
    return read_meta(path)


def _migrate(engine: Engine, state: dict, from_v: str, to_v: str) -> dict:
    fn = getattr(engine.mock.handlers, "migrate_state", None) if engine.mock.handlers else None
    if fn is None:
        raise SnapshotError(
            f"snapshot is mock version {from_v} but engine is {to_v}, and the mock declares no "
            f"migrate_state(state, from_version, to_version) — cannot safely load"
        )
    migrated = fn(state, from_v, to_v)
    if not isinstance(migrated, dict):
        raise SnapshotError("migrate_state must return the migrated state dict")
    return migrated
