"""Registry gate (REQ-REG-*): offline add/search/pin/checksum/safety."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from mockworld.registry import RegistryClient, RegistryError, dir_checksum

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "registry"


@pytest.fixture
def local_registry(tmp_path, monkeypatch):
    """A local registry index + a MOCKWORLD_HOME install dir, all offline."""
    monkeypatch.setenv("MOCKWORLD_HOME", str(tmp_path / "home"))
    return RegistryClient(str(EXAMPLE / "registry.json"))


def test_search_finds_weather(local_registry):
    hits = local_registry.search("weather")
    assert any(e.name == "weather" for e in hits)


def test_add_installs_and_runs(local_registry, monkeypatch):
    from mockworld import Engine, list_installed_mocks

    dest = local_registry.add("weather")
    assert (dest / "mock.yaml").exists()
    assert "weather" in list_installed_mocks()
    # the installed mock resolves and runs deterministically
    e = Engine.from_source("mock:weather", seed=7, faults="none")
    assert e.call("list_stations", {}).data["count"] == 25


def test_pin_unknown_version_errors(local_registry):
    with pytest.raises(RegistryError):
        local_registry.resolve("weather@9.9.9")


def test_checksum_mismatch_is_rejected(local_registry, tmp_path, monkeypatch):
    # Point the client at a tampered index whose sha256 won't match the source.
    bad_index = tmp_path / "registry.json"
    data = json.loads((EXAMPLE / "registry.json").read_text())
    data["mocks"][0]["sha256"] = "0" * 64
    data["mocks"][0]["source"] = str(EXAMPLE / "mocks" / "weather")
    bad_index.write_text(json.dumps(data))
    client = RegistryClient(str(bad_index))
    with pytest.raises(RegistryError, match="checksum mismatch"):
        client.add("weather")


def test_safety_gate_blocks_network_imports(local_registry, tmp_path):
    # A community mock whose handler reaches for the network must be refused.
    evil = tmp_path / "evil"
    shutil.copytree(EXAMPLE / "mocks" / "weather", evil)
    (evil / "handlers.py").write_text(
        "import socket\nfrom mockworld import Result\n"
        "def get_forecast(ctx, params):\n    return Result.ok({})\n"
    )
    index = tmp_path / "registry.json"
    index.write_text(json.dumps({"mocks": [
        {"name": "evil", "version": "0.1.0", "source": str(evil)}
    ]}))
    with pytest.raises(RegistryError, match="socket"):
        RegistryClient(str(index)).add("evil")


def test_checksum_is_stable():
    a = dir_checksum(EXAMPLE / "mocks" / "weather")
    b = dir_checksum(EXAMPLE / "mocks" / "weather")
    assert a == b and len(a) == 64
