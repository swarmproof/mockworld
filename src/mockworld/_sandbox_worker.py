"""Sandbox worker — runs ONE untrusted mock's code in a hardened subprocess.

Launched by :mod:`mockworld.sandbox` as ``python -m mockworld._sandbox_worker <dir>``.
Everything untrusted (importing ``handlers.py``/``seed.py`` and running them) happens
here, never in the parent. Before any untrusted import we neuter the network,
subprocess/exec, ctypes, and file writes, and apply CPU/memory limits.

This is defense-in-depth, not a formal guarantee: in-process Python can't be made
perfectly escape-proof. It removes the easy paths (exfiltration, spawning
processes, trashing files) and contains crashes/hangs to a disposable child that
holds none of the parent's state. For hard isolation, run mockworld in a container.

Protocol: length-prefixed JSON (4-byte big-endian length + UTF-8 body) on a private
fd duped from stdout; the child's own stdout is redirected to stderr so handler
`print()`s can't corrupt the stream.
"""

from __future__ import annotations

import builtins
import json
import os
import struct
import sys
from pathlib import Path


def _harden() -> None:
    """Neuter dangerous capabilities on already-imported modules, then lock limits."""
    def blocked(*_a, **_k):
        raise PermissionError("blocked in mockworld sandbox")

    import socket
    socket.socket = blocked
    socket.create_connection = blocked
    socket.create_server = blocked

    import subprocess
    for fn in ("Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"):
        if hasattr(subprocess, fn):
            setattr(subprocess, fn, blocked)

    for fn in ("system", "popen", "fork", "forkpty", "exec", "execv", "execve", "execvp",
               "execvpe", "execl", "execle", "execlp", "execlpe", "spawnv", "spawnve",
               "spawnl", "spawnlp", "remove", "unlink", "rmdir", "removedirs", "rename",
               "replace", "truncate", "kill", "killpg"):
        if hasattr(os, fn):
            setattr(os, fn, blocked)

    try:
        import ctypes
        for fn in ("CDLL", "PyDLL", "WinDLL", "OleDLL", "cdll", "pydll", "windll"):
            if hasattr(ctypes, fn):
                setattr(ctypes, fn, blocked)
    except Exception:
        pass

    real_open = builtins.open

    def safe_open(file, mode="r", *a, **k):
        if any(c in mode for c in "wax+"):
            raise PermissionError("file writes are blocked in the mockworld sandbox")
        return real_open(file, mode, *a, **k)

    builtins.open = safe_open

    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (5, 6))  # ~5 CPU-seconds per worker
        mem = 512 * 1024 * 1024
        for lim in ("RLIMIT_AS", "RLIMIT_DATA"):
            if hasattr(resource, lim):
                try:
                    resource.setrlimit(getattr(resource, lim), (mem, mem))
                except (ValueError, OSError):
                    pass
    except Exception:
        pass


def _read_msg(stream) -> dict | None:
    header = stream.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack(">I", header)
    return json.loads(stream.read(length))


def _write_msg(stream, obj: dict) -> None:
    body = json.dumps(obj).encode()
    stream.write(struct.pack(">I", len(body)))
    stream.write(body)
    stream.flush()


def _result_payload(result) -> dict:
    if result.success:
        return {"success": True, "data": result.data, "meta": result.meta}
    err = result.err
    return {"success": False, "error": {
        "code": err.code, "message": err.message, "http_status": err.http_status,
        "body": err.body, "retry_after_s": err.retry_after_s}}


def main() -> None:
    mock_dir = Path(sys.argv[1])

    # Private protocol channel; keep the real stdout clean.
    proto_out = os.fdopen(os.dup(1), "wb")
    inp = sys.stdin.buffer
    sys.stdout = sys.stderr

    _harden()  # <-- everything below runs under the neutered environment

    import yaml

    from mockworld.datagen import DataGen
    from mockworld.determinism import DeterministicContext
    from mockworld.errors import register_error
    from mockworld.handler_ctx import FaultHelper, HandlerCtx
    from mockworld.loader import SeedCtx, _import_module
    from mockworld.schema import MockDef
    from mockworld.state import _TOMBSTONE, StateView

    definition = MockDef.model_validate(yaml.safe_load((mock_dir / "mock.yaml").read_text()))
    for name, template in definition.errors.items():
        register_error(name, template)
    handlers = _import_module(mock_dir / "handlers.py", "sbx_handlers")
    seed_module = _import_module(mock_dir / "seed.py", "sbx_seed")

    def handle(req: dict) -> dict:
        op = req["op"]
        dctx = DeterministicContext(req["seed"])

        if op == "seed":
            seed_ctx = SeedCtx(rng=dctx.seed_rng(), ids=dctx.ids_for("__seed__", 0),
                               fake=DataGen(dctx.seed_rng()))
            if definition.seed.generator.startswith("python:") and seed_module is not None:
                fn = getattr(seed_module, definition.seed.generator.split(".", 1)[-1])
                snapshot = fn(seed_ctx, definition)
            else:
                snapshot = {}  # builtin seed handled parent-side (trusted code)
            return {"ok": True, "snapshot": snapshot}

        if op == "call":
            tool = definition.tool(req["tool"])
            fn = getattr(handlers, tool.handler_name, None) if handlers else None
            if fn is None:
                return {"ok": True, "result": {"success": False, "error": {
                    "code": "internal_error", "message": f"handler {tool.handler_name!r} not found",
                    "http_status": 500, "body": {}, "retry_after_s": None}},
                    "mutations": {}, "deletes": {}}

            view = StateView(req["state"], {}, list(req["state"].keys()))
            ctx = HandlerCtx(state=view, clock=dctx.clock_for(req["step"]),
                             ids=dctx.ids_for(req["tool"], req["idx"]),
                             rng=dctx.rng_for(req["tool"], req["idx"]),
                             tool=req["tool"], faults=FaultHelper())
            result = fn(ctx, req["params"])

            mutations: dict = {}
            deletes: dict = {}
            for coll, entries in view._scratch.items():
                for key, value in entries.items():
                    if value is _TOMBSTONE:
                        deletes.setdefault(coll, []).append(key)
                    else:
                        mutations.setdefault(coll, {})[key] = value
            return {"ok": True, "result": _result_payload(result),
                    "mutations": mutations, "deletes": deletes}

        return {"ok": False, "error": f"unknown op {op!r}"}

    while True:
        req = _read_msg(inp)
        if req is None:
            break
        try:
            resp = handle(req)
        except Exception as exc:  # never crash the worker on handler error
            resp = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        _write_msg(proto_out, resp)


if __name__ == "__main__":
    main()
