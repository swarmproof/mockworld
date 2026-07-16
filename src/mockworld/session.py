"""Session lifecycle and per-session logical position (ARCHITECTURE §6; REQ-ISO-*).

A session owns its copy-on-write overlay (in the store) plus the mutable counters
that advance its logical timeline: a per-tool call index (so each tool's fault
substream is independent, DT-7) and a monotonic clock step. Both start at zero
per session, so a session replaying a script sees the same ids/timestamps as a
solo run (REQ-ISO-3).
"""

from __future__ import annotations

from .state import StateStore


class Session:
    __slots__ = ("id", "_tool_idx", "_clock_step")

    def __init__(self, session_id: str) -> None:
        self.id = session_id
        self._tool_idx: dict[str, int] = {}
        self._clock_step = 0

    def next_call(self, tool_name: str) -> tuple[int, int]:
        """Advance this session's clocks for one call → ``(per_tool_index, clock_step)``."""
        idx = self._tool_idx.get(tool_name, 0)
        self._tool_idx[tool_name] = idx + 1
        step = self._clock_step
        self._clock_step += 1
        return idx, step

    def reset(self) -> None:
        self._tool_idx.clear()
        self._clock_step = 0


class SessionManager:
    """Creates, isolates, resets and GCs sessions keyed on ``Mcp-Session-Id`` (ADR-2)."""

    def __init__(self, store: StateStore) -> None:
        self._store = store
        self._sessions: dict[str, Session] = {}

    def get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            session = Session(session_id)
            self._sessions[session_id] = session
            self._store.ensure_session(session_id)
        return session

    def reset_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].reset()
        self._store.session_reset(session_id)

    def close(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._store.close_session(session_id)

    def reset_all(self) -> None:
        self._sessions.clear()
        self._store.reset()

    def count(self) -> int:
        return len(self._sessions)
