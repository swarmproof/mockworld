"""The single seeded entropy funnel (ARCHITECTURE §5.2, ADR-4).

Every source of nondeterminism in mockworld — clock, IDs, RNG, and the fault
"dice" — is derived here from one integer seed. No other module may read the
wall clock, call ``random`` without a seed, use ``uuid``, or rely on dict-hash
order. ``mockworld validate`` lints handlers for violations of that rule.

Derivation is by stable BLAKE2b hash of a key tuple, never Python's built-in
``hash()`` (which is salted per-process and would break cross-host replay,
REQ-DET-6). Values are keyed on ``(seed, tool_name, per-tool-call-index, ...)``
and deliberately *not* on session identity, so that two sessions replaying the
same script produce byte-identical transcripts (REQ-ISO-3 / test ISO-3) while
isolation is provided purely by the copy-on-write state layer.
"""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime

# A fixed anchor so timestamps look real (≈ 2023-11-14) but stay seed-derived.
_BASE_EPOCH = 1_700_000_000
# Logical seconds the virtual clock advances per tool call.
_CLOCK_STEP_S = 7

_BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _base62(n: int, width: int = 0) -> str:
    if n == 0:
        s = "0"
    else:
        chars = []
        while n:
            n, rem = divmod(n, 62)
            chars.append(_BASE62[rem])
        s = "".join(reversed(chars))
    return s.rjust(width, "0")


class Clock:
    """A virtual clock frozen at one logical instant for the duration of a call.

    Timestamps are unix epoch **seconds** (Stripe-shaped). The engine constructs
    a fresh ``Clock`` per tool call from the session's advancing logical time, so
    a handler that calls ``now()`` twice sees the same instant (REQ-DET-2).
    """

    __slots__ = ("_epoch",)

    def __init__(self, epoch_seconds: int) -> None:
        self._epoch = epoch_seconds

    def now(self) -> int:
        """Unix epoch seconds (int)."""
        return self._epoch

    def now_ms(self) -> int:
        return self._epoch * 1000

    def iso(self) -> str:
        return datetime.fromtimestamp(self._epoch, tz=UTC).isoformat()


class IdGen:
    """Deterministic identifier generator bound to one tool call.

    ``next("ch")`` → ``"ch_<base62>"``. The suffix is a stable hash of
    ``(seed, tool_name, call_index, prefix, local_seq)`` so ids are unique within
    a session's logical timeline and identical across sessions replaying the same
    script (REQ-DET-3).
    """

    __slots__ = ("_ctx", "_tool", "_idx", "_local")

    def __init__(self, ctx: "DeterministicContext", tool: str, idx: int) -> None:
        self._ctx = ctx
        self._tool = tool
        self._idx = idx
        self._local = 0

    def next(self, prefix: str) -> str:
        self._local += 1
        n = self._ctx.stable_hash("id", self._tool, self._idx, prefix, self._local)
        return f"{prefix}_{_base62(n, width=11)}"


class DeterministicContext:
    """Global, seed-bound derivation. Stateless with respect to a run.

    Per-session mutable position (per-tool call counters, the clock step) lives on
    :class:`~mockworld.session.Session`; this object only turns a key into a value.
    """

    def __init__(self, seed: int) -> None:
        self.seed = int(seed)
        # Different seeds produce different — but still fully determined — clocks.
        self.base_epoch = _BASE_EPOCH + (self.seed % 1_000_000)

    def stable_hash(self, *parts: object) -> int:
        """A host-stable 64-bit hash of ``(seed, *parts)``. Never ``hash()``."""
        h = hashlib.blake2b(digest_size=8)
        h.update(str(self.seed).encode())
        for p in parts:
            h.update(b"\x1f")  # unit separator, avoids "a|b" == "a" + "|b" collisions
            h.update(str(p).encode())
        return int.from_bytes(h.digest(), "big")

    # -- per-call entropy sources ------------------------------------------------

    def clock_for(self, step: int) -> Clock:
        return Clock(self.base_epoch + step * _CLOCK_STEP_S)

    def ids_for(self, tool: str, idx: int) -> IdGen:
        return IdGen(self, tool, idx)

    def rng_for(self, tool: str, idx: int) -> random.Random:
        """A fresh seeded PRNG for a handler, on its own substream.

        Mersenne Twister seeded with an int is reproducible across hosts and
        Python versions, satisfying REQ-DET-6.
        """
        return random.Random(self.stable_hash("rng", tool, idx))

    def dice(self, tool: str, idx: int, rule_index: int) -> float:
        """A fault die in ``[0, 1)`` on an independent substream (ARCHITECTURE §5.2).

        Keyed on ``(tool, call-index, rule)`` so inserting an unrelated tool call
        cannot shift another tool's fault sequence (test DT-7).
        """
        return self.stable_hash("fault", tool, idx, rule_index) / 2**64

    def seed_rng(self) -> random.Random:
        """The PRNG for one-time base-dataset generation (seed.py)."""
        return random.Random(self.stable_hash("seed-data"))
