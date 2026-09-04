"""Parent-side driver for the untrusted-handler sandbox (ADR-7 v0.2b; REQ-REG-3).

Manages one persistent hardened subprocess per untrusted mock (see
:mod:`mockworld._sandbox_worker`) and exchanges length-prefixed JSON with it. The
parent keeps ownership of state and entropy: it derives the per-call keys, ships
the state slice + params, and applies the returned mutations to its own
copy-on-write overlay — so a sandboxed mock is byte-identical to a trusted one,
and isolation still lives in the parent.
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

from .errors import MockError, Result


class SandboxError(Exception):
    pass


class SandboxWorker:
    def __init__(self, mock_dir: Path, timeout: float = 15.0) -> None:
        self.mock_dir = Path(mock_dir)
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None

    def _ensure(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "mockworld._sandbox_worker", str(self.mock_dir)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )
        return self._proc

    def _rpc(self, request: dict) -> dict:
        proc = self._ensure()
        assert proc.stdin and proc.stdout
        body = json.dumps(request).encode()
        try:
            proc.stdin.write(struct.pack(">I", len(body)))
            proc.stdin.write(body)
            proc.stdin.flush()
            header = proc.stdout.read(4)
            if len(header) < 4:
                raise SandboxError("sandbox worker exited unexpectedly "
                                   "(possibly killed by a resource limit)")
            (length,) = struct.unpack(">I", header)
            resp = json.loads(proc.stdout.read(length))
        except (BrokenPipeError, struct.error) as exc:
            self.close()
            raise SandboxError(f"sandbox worker communication failed: {exc}") from exc
        if not resp.get("ok"):
            raise SandboxError(resp.get("error", "sandbox worker error"))
        return resp

    # -- operations --------------------------------------------------------------

    def seed(self, seed: int) -> dict[str, Any]:
        return self._rpc({"op": "seed", "seed": seed})["snapshot"]

    def call(self, *, seed: int, tool: str, idx: int, step: int,
             state: dict, params: dict) -> tuple[Result, dict, dict]:
        resp = self._rpc({"op": "call", "seed": seed, "tool": tool, "idx": idx,
                          "step": step, "state": state, "params": params})
        return _to_result(resp["result"]), resp["mutations"], resp["deletes"]

    def close(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None


def _to_result(payload: dict) -> Result:
    if payload["success"]:
        r = Result.ok(payload.get("data"))
        r.meta = payload.get("meta", {})
        return r
    e = payload["error"]
    return Result.from_error(MockError(code=e["code"], message=e["message"],
                                       http_status=e["http_status"], body=e["body"],
                                       retry_after_s=e.get("retry_after_s")))
