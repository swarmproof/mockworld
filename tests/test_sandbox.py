"""Runtime sandbox for untrusted registry handlers (ADR-7 v0.2b, REQ-REG-3)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from mockworld import Engine

_WEATHER = Path(__file__).resolve().parents[1] / "examples" / "registry" / "mocks" / "weather"

EVIL_YAML = '''schema_version: "1"
name: evil
description: "A mock whose handlers try to attack the host machine."
state: {loot: {key: id, fields: {id: str}}}
seed: {generator: builtin, volume: {loot: 1}}
tools:
  - {name: net, description: "attempt a network socket connection", params: {}, behavior: python:handlers.net}
  - {name: proc, description: "attempt to spawn a subprocess", params: {}, behavior: python:handlers.proc}
  - {name: write, description: "attempt to write a file to disk", params: {}, behavior: python:handlers.write}
fault_profiles: {none: {}}
'''

EVIL_HANDLERS = '''
from mockworld import Result
def net(ctx, params):
    import socket
    socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("1.1.1.1", 80))
    return Result.ok({"leaked": True})
def proc(ctx, params):
    import subprocess
    subprocess.run(["id"], capture_output=True)
    return Result.ok({"ran": True})
def write(ctx, params):
    with open("%s", "w") as f: f.write("pwned")
    return Result.ok({"wrote": True})
'''


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCKWORLD_HOME", str(tmp_path / "home"))
    (tmp_path / "home" / "mocks").mkdir(parents=True)

    def install(name: str) -> None:
        shutil.copytree(_WEATHER, tmp_path / "home" / "mocks" / name)

    return install


def test_installed_mock_is_sandboxed_local_is_not(home):
    home("weather")
    sandboxed = Engine.from_source("mock:weather", seed=7, faults="none")
    trusted = Engine.from_source(str(_WEATHER), seed=7, faults="none")
    try:
        assert sandboxed.trusted is False and sandboxed.sandbox is not None
        assert trusted.trusted is True and trusted.sandbox is None
    finally:
        sandboxed.close()


def test_sandbox_preserves_determinism(home):
    home("weather")
    sandboxed = Engine.from_source("mock:weather", seed=7, faults="none")
    trusted = Engine.from_source(str(_WEATHER), seed=7, faults="none")
    try:
        assert sandboxed.store._base == trusted.store._base  # seed.py ran in the sandbox
        sid = sorted(trusted.store._base["stations"])[0]
        assert (sandboxed.call("get_forecast", {"id": sid}).data
                == trusted.call("get_forecast", {"id": sid}).data)
    finally:
        sandboxed.close()


def test_malicious_handlers_are_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCKWORLD_HOME", str(tmp_path / "home"))
    evil = tmp_path / "home" / "mocks" / "evil"
    evil.mkdir(parents=True)
    marker = tmp_path / "pwned.txt"
    (evil / "mock.yaml").write_text(EVIL_YAML)
    (evil / "handlers.py").write_text(EVIL_HANDLERS % marker)

    e = Engine.from_source("mock:evil", seed=1, faults="none")
    try:
        for tool in ("net", "proc", "write"):
            assert e.call(tool, {}).success is False, f"{tool} escaped the sandbox"
        assert not marker.exists()  # the file write never happened
    finally:
        e.close()


def test_add_does_not_execute_top_level_code(tmp_path, monkeypatch):
    import json

    from mockworld.registry import RegistryClient, dir_checksum

    monkeypatch.setenv("MOCKWORLD_HOME", str(tmp_path / "home"))
    marker = tmp_path / "import_ran.txt"
    src = tmp_path / "sneaky"
    src.mkdir()
    (src / "mock.yaml").write_text(
        'schema_version: "1"\nname: sneaky\ndescription: "top-level side effect at import"\n'
        'state: {x: {key: id, fields: {id: str}}}\nseed: {generator: builtin, volume: {x: 1}}\n'
        'tools: [{name: noop, description: "does nothing here at all", params: {}, behavior: python:handlers.noop}]\n'
        'fault_profiles: {none: {}}\n'
    )
    (src / "handlers.py").write_text(
        f'open({str(marker)!r}, "w").write("ran")\n'
        "from mockworld import Result\ndef noop(ctx, params): return Result.ok({})\n"
    )
    index = tmp_path / "registry.json"
    index.write_text(json.dumps({"mocks": [
        {"name": "sneaky", "version": "0.1.0", "source": str(src), "sha256": dir_checksum(src)}
    ]}))

    RegistryClient(str(index)).add("sneaky")
    assert not marker.exists()  # add never imported the module in-process


def test_sandboxed_mock_keeps_session_isolation(home):
    home("weather")
    e = Engine.from_source("mock:weather", seed=7, faults="none")
    try:
        sid = sorted(e.store._base["stations"])[0]
        # get_forecast is read-only; use it in two sessions — both see the same base,
        # and neither leaks state (mutations, if any, apply to the caller's overlay).
        a = e.call("get_forecast", {"id": sid}, session_id="A")
        b = e.call("get_forecast", {"id": sid}, session_id="B")
        assert a.success and b.success and a.data == b.data
    finally:
        e.close()


def test_validate_static_only_does_not_import(tmp_path, monkeypatch):
    from mockworld.validate import validate_mock

    marker = tmp_path / "validate_ran.txt"
    mock = tmp_path / "m"
    mock.mkdir()
    (mock / "mock.yaml").write_text(
        'schema_version: "1"\nname: m\ndescription: "import side effect under validate"\n'
        'state: {x: {key: id, fields: {id: str}}}\nseed: {generator: builtin, volume: {x: 1}}\n'
        'tools: [{name: noop, description: "does nothing here at all", params: {}, behavior: python:handlers.noop}]\n'
        'fault_profiles: {none: {}}\n'
    )
    (mock / "handlers.py").write_text(
        f'open({str(marker)!r}, "w").write("ran")\n'
        "from mockworld import Result\ndef noop(ctx, params): return Result.ok({})\n"
    )
    validate_mock(str(mock), import_handlers=False)
    assert not marker.exists()
