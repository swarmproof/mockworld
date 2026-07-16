"""The handler ABI context (ARCHITECTURE §4.3; REQ-DEF-4).

A handler is ``def fn(ctx, params) -> Result``. ``ctx`` exposes the *only* legal
entropy sources — ``clock``, ``ids``, ``rng`` — plus a copy-on-write ``state``
view scoped to this session. A handler that imports ``time``/``random``/``uuid``
breaks the determinism contract and is flagged by ``mockworld validate``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .determinism import Clock, IdGen
from .errors import Result
from .state import StateView


class FaultHelper:
    """Lets a handler raise a declared/named fault conditionally."""

    def error(self, code: str, message: str | None = None, **overrides: object) -> Result:
        return Result.error(code, message, **overrides)


@dataclass
class HandlerCtx:
    state: StateView
    clock: Clock
    ids: IdGen
    rng: random.Random
    tool: str
    faults: FaultHelper

    def now(self) -> int:
        """Virtual-clock unix seconds — never the wall clock (REQ-DET-2)."""
        return self.clock.now()
