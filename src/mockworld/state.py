"""State store and copy-on-write session isolation (ARCHITECTURE §5.1, §6; ADR-3).

Three layers stack per tool call:

    base (seeded once, immutable)  <  session overlay (persists per session)  <  call scratch

Reads fall through top-to-bottom; writes land in the call scratch and are
committed into the session overlay atomically only if the call succeeds
(REQ-STATE-3). Because the base is shared read-only, 50+ parallel sessions cost
one dataset plus small per-session deltas (REQ-ISO-3).

``MemoryStore`` and ``SQLiteStore`` share this merge logic verbatim; the store
conformance suite (test DT-5) asserts they behave identically. SQLite adds a
portable on-disk snapshot artifact (REQ-SNAP-*).
"""

from __future__ import annotations

import copy
import json
import sqlite3
from abc import ABC, abstractmethod
from typing import Any, Iterable

# Sentinel marking a key deleted in an overlay/scratch so it hides a base entity.
_TOMBSTONE = object()

Entity = dict[str, Any]
CollectionData = dict[str, Any]  # key -> Entity (or _TOMBSTONE in an overlay)
Snapshot = dict[str, dict[str, Entity]]


class CollectionView:
    """Handler-facing accessor for one collection through the CoW stack.

    Bound to a :class:`StateView`; every mutation is staged in the call scratch.
    """

    __slots__ = ("_view", "_name")

    def __init__(self, view: "StateView", name: str) -> None:
        self._view = view
        self._name = name

    def get(self, key: str) -> Entity | None:
        return self._view._read(self._name, key)

    def exists(self, key: str) -> bool:
        return self._view._read(self._name, key) is not None

    def put(self, key: str, obj: Entity) -> Entity:
        self._view._write(self._name, key, obj)
        return obj

    def delete(self, key: str) -> bool:
        existed = self.exists(key)
        self._view._delete(self._name, key)
        return existed

    def all(self) -> list[Entity]:
        """Every live entity, sorted by key for stable iteration (REQ-DET-4)."""
        return [self._view._read(self._name, k) for k in self._view._keys(self._name)]

    def keys(self) -> list[str]:
        return self._view._keys(self._name)

    def count(self) -> int:
        return len(self._view._keys(self._name))

    def find(self, **filters: Any) -> Entity | None:
        for e in self.all():
            if all(e.get(k) == v for k, v in filters.items()):
                return e
        return None

    def filter(self, **filters: Any) -> list[Entity]:
        return [e for e in self.all() if all(e.get(k) == v for k, v in filters.items())]


class StateView:
    """A copy-on-write view of one session's state for the span of one call."""

    def __init__(
        self,
        base: Snapshot,
        overlay: dict[str, CollectionData],
        collections: Iterable[str],
    ) -> None:
        self._base = base
        self._overlay = overlay
        self._scratch: dict[str, CollectionData] = {}
        self._collections = set(collections)

    def __getattr__(self, name: str) -> CollectionView:
        # Attribute access (ctx.state.customers) maps to a declared collection.
        if name.startswith("_") or name not in self._collections:
            raise AttributeError(f"no such collection: {name!r}")
        return CollectionView(self, name)

    def collection(self, name: str) -> CollectionView:
        if name not in self._collections:
            raise AttributeError(f"no such collection: {name!r}")
        return CollectionView(self, name)

    # -- internal CoW mechanics --------------------------------------------------

    def _read(self, coll: str, key: str) -> Entity | None:
        for layer in (self._scratch, self._overlay):
            if coll in layer and key in layer[coll]:
                v = layer[coll][key]
                return None if v is _TOMBSTONE else copy.deepcopy(v)
        v = self._base.get(coll, {}).get(key)
        return copy.deepcopy(v) if v is not None else None

    def _write(self, coll: str, key: str, obj: Entity) -> None:
        self._scratch.setdefault(coll, {})[key] = copy.deepcopy(obj)

    def _delete(self, coll: str, key: str) -> None:
        self._scratch.setdefault(coll, {})[key] = _TOMBSTONE

    def _keys(self, coll: str) -> list[str]:
        live: dict[str, bool] = {}
        for k in self._base.get(coll, {}):
            live[k] = True
        for layer in (self._overlay, self._scratch):
            for k, v in layer.get(coll, {}).items():
                live[k] = v is not _TOMBSTONE
        return sorted(k for k, ok in live.items() if ok)

    def has_changes(self) -> bool:
        return bool(self._scratch)

    def commit(self) -> None:
        """Merge staged writes into the session overlay (atomic per call)."""
        for coll, entries in self._scratch.items():
            self._overlay.setdefault(coll, {}).update(entries)
        self._scratch = {}

    def rollback(self) -> None:
        self._scratch = {}


class StateStore(ABC):
    """Base dataset + per-session copy-on-write overlays."""

    def __init__(self, collections: Iterable[str]) -> None:
        self._collections = list(collections)
        self._base: Snapshot = {c: {} for c in self._collections}
        self._overlays: dict[str, dict[str, CollectionData]] = {}

    # -- base seeding ------------------------------------------------------------

    def load_base(self, data: Snapshot) -> None:
        """Install the seeded base dataset (called once at boot / on reset)."""
        self._base = {c: dict(data.get(c, {})) for c in self._collections}

    def reset(self) -> None:
        """Drop all overlays; base is regenerated by the caller (REQ-DET-5)."""
        self._overlays.clear()

    # -- session lifecycle -------------------------------------------------------

    def ensure_session(self, session_id: str) -> None:
        self._overlays.setdefault(session_id, {})

    def session_reset(self, session_id: str) -> None:
        """Drop one session's overlay, leaving siblings untouched (REQ-ISO-4)."""
        self._overlays[session_id] = {}

    def install_overlay(self, session_id: str, state: Snapshot) -> None:
        """Replace a session's overlay wholesale (used to restore a snapshot)."""
        self._overlays[session_id] = {c: dict(v) for c, v in state.items()}

    def close_session(self, session_id: str) -> None:
        self._overlays.pop(session_id, None)

    def session_count(self) -> int:
        return len(self._overlays)

    def view(self, session_id: str) -> StateView:
        self.ensure_session(session_id)
        return StateView(self._base, self._overlays[session_id], self._collections)

    # -- snapshots (portable state artifacts) ------------------------------------

    def snapshot_dict(self, session_id: str) -> Snapshot:
        """Materialize a session's full effective state as a plain dict."""
        view = self.view(session_id)
        return {c: {k: view._read(c, k) for k in view._keys(c)} for c in self._collections}

    @abstractmethod
    def persist(self, session_id: str, path: str) -> None:
        ...

    @abstractmethod
    def restore(self, session_id: str, path: str) -> None:
        ...


class MemoryStore(StateStore):
    """Fastest store; ephemeral. The v0.1 default (ADR-3)."""

    def persist(self, session_id: str, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.snapshot_dict(session_id), f)

    def restore(self, session_id: str, path: str) -> None:
        with open(path) as f:
            data = json.load(f)
        self._overlays[session_id] = {c: dict(v) for c, v in data.items()}


class SQLiteStore(StateStore):
    """Same CoW semantics as :class:`MemoryStore`, with a portable SQLite snapshot.

    Working state is held in RAM for parity and speed (per-call SQL would violate
    NFR-PERF-2); ``persist``/``restore`` serialize a full session snapshot to a
    single-table SQLite file — an inspectable artifact shareable in bug reports
    (REQ-SNAP-1..3).
    """

    def persist(self, session_id: str, path: str) -> None:
        snap = self.snapshot_dict(session_id)
        conn = sqlite3.connect(path)
        try:
            conn.execute("DROP TABLE IF EXISTS state")
            conn.execute(
                "CREATE TABLE state (collection TEXT, key TEXT, value TEXT, "
                "PRIMARY KEY (collection, key))"
            )
            rows = [
                (coll, key, json.dumps(entity))
                for coll, entities in snap.items()
                for key, entity in entities.items()
            ]
            conn.executemany("INSERT INTO state VALUES (?, ?, ?)", rows)
            conn.commit()
        finally:
            conn.close()

    def restore(self, session_id: str, path: str) -> None:
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute("SELECT collection, key, value FROM state").fetchall()
        finally:
            conn.close()
        overlay: dict[str, CollectionData] = {}
        for coll, key, value in rows:
            overlay.setdefault(coll, {})[key] = json.loads(value)
        self._overlays[session_id] = overlay


def make_store(kind: str, collections: Iterable[str]) -> StateStore:
    if kind == "memory":
        return MemoryStore(collections)
    if kind == "sqlite":
        return SQLiteStore(collections)
    raise ValueError(f"unknown state store: {kind!r} (expected 'memory' or 'sqlite')")
