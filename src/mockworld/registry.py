"""Mock registry — the network-effect moat (ARCHITECTURE §8; REQ-REG-*).

v0.2a is *index-as-repo*: a ``registry.json`` (awesome-list DNA) maps
``mock:<name>`` → source + version + checksum. ``mockworld add`` resolves, pins,
fetches, verifies the sha256, runs a safety gate, and installs into
``~/.mockworld/mocks``. The index and sources can be local paths, ``file://``, or
``https://`` — so everything is testable offline (NFR-OFFLINE-1).

Provenance & safety (REQ-REG-3, NFR-SEC-1): installs verify a content checksum
and statically reject handler code that reaches for the network or subprocesses
— the lightweight "sandboxed by default" stance for untrusted community code,
ahead of full subprocess/WASM isolation (ADR-7, v0.2b). Locally-authored mocks
stay trusted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .loader import installed_dir
from .validate import validate_mock

DEFAULT_REGISTRY = os.environ.get(
    "MOCKWORLD_REGISTRY",
    "https://raw.githubusercontent.com/swarmproof/mockworld-registry/main/registry.json",
)

# Imports that let untrusted handler code escape the sandbox (REQ-REG-3).
_UNSAFE_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(socket|subprocess|requests|urllib|http|httpx|ftplib|"
    r"smtplib|ctypes|multiprocessing|shutil|pathlib|os|sys)\b",
    re.M,
)


class RegistryError(Exception):
    pass


@dataclass
class RegistryEntry:
    name: str
    version: str
    source: str            # dir path | file:// | https:// (tarball) | git+https://
    sha256: str | None = None
    description: str = ""
    fidelity: str = "partial"
    tools: int = 0


def dir_checksum(path: Path) -> str:
    """Deterministic sha256 over a mock directory's files (names + contents)."""
    h = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        rel = f.relative_to(path).as_posix()
        h.update(rel.encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


class RegistryClient:
    def __init__(self, index_url: str = DEFAULT_REGISTRY) -> None:
        self.index_url = index_url

    # -- index ------------------------------------------------------------------

    def _load_index(self) -> dict[str, list[RegistryEntry]]:
        raw = self._read(self.index_url)
        data = json.loads(raw)
        entries = data["mocks"] if isinstance(data, dict) and "mocks" in data else data
        by_name: dict[str, list[RegistryEntry]] = {}
        for e in entries:
            entry = RegistryEntry(
                name=e["name"], version=e.get("version", "0.0.0"), source=e["source"],
                sha256=e.get("sha256"), description=e.get("description", ""),
                fidelity=e.get("fidelity", "partial"), tools=e.get("tools", 0),
            )
            by_name.setdefault(entry.name, []).append(entry)
        for versions in by_name.values():
            versions.sort(key=lambda x: _semver_key(x.version), reverse=True)
        return by_name

    def search(self, term: str) -> list[RegistryEntry]:
        term = term.lower()
        latest = [v[0] for v in self._load_index().values()]
        hits = [e for e in latest if term in e.name.lower() or term in e.description.lower()]
        return sorted(hits, key=lambda e: e.name)

    def resolve(self, spec: str) -> RegistryEntry:
        name, _, pin = spec.partition("@")
        versions = self._load_index().get(name)
        if not versions:
            raise RegistryError(f"no such mock in registry: {name!r}")
        if pin:
            match = next((e for e in versions if e.version == pin), None)
            if match is None:
                raise RegistryError(f"{name}@{pin} not found; have {[e.version for e in versions]}")
            return match
        return versions[0]  # latest

    # -- install ----------------------------------------------------------------

    def add(self, spec: str, *, force: bool = False, trust: bool = False) -> Path:
        entry = self.resolve(spec)
        dest = installed_dir() / entry.name
        if dest.exists() and not force:
            raise RegistryError(f"{entry.name} already installed (use force=True to reinstall)")

        with tempfile.TemporaryDirectory() as tmp:
            staged = self._fetch(entry, Path(tmp))

            if entry.sha256:
                actual = dir_checksum(staged)
                if actual != entry.sha256:
                    raise RegistryError(
                        f"checksum mismatch for {entry.name}: expected {entry.sha256[:12]}…, "
                        f"got {actual[:12]}…"
                    )

            findings = validate_mock(str(staged))
            errors = [f.message for f in findings if f.level == "error"]
            if errors:
                raise RegistryError(f"{entry.name} failed validation: {errors}")

            if not trust:
                self._safety_gate(staged)

            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(staged, dest, ignore=shutil.ignore_patterns("__pycache__"))
        return dest

    def _safety_gate(self, mock_dir: Path) -> None:
        for py in mock_dir.glob("*.py"):
            m = _UNSAFE_IMPORT.search(py.read_text())
            if m:
                raise RegistryError(
                    f"{py.name} imports {m.group(1)!r} — registry handler code may not reach "
                    f"the network/filesystem/processes (install a trusted local copy instead)"
                )

    # -- fetch backends ---------------------------------------------------------

    def _fetch(self, entry: RegistryEntry, into: Path) -> Path:
        src = entry.source
        if src.startswith("git+"):
            return self._fetch_git(src[4:], into)
        parsed = urlparse(src)
        if parsed.scheme in ("http", "https", "file") and src.endswith((".tar.gz", ".tgz")):
            return self._fetch_tarball(src, into)
        # plain path (possibly relative to the index file for local registries)
        path = Path(parsed.path if parsed.scheme == "file" else src)
        if not path.is_absolute() and not path.exists():
            base = Path(urlparse(self.index_url).path if self.index_url.startswith("file") else self.index_url)
            path = (base.parent / src).resolve()
        if not (path / "mock.yaml").exists():
            raise RegistryError(f"source has no mock.yaml: {path}")
        return path

    def _fetch_tarball(self, url: str, into: Path) -> Path:
        data = self._read_bytes(url)
        archive = into / "mock.tar.gz"
        archive.write_bytes(data)
        with tarfile.open(archive) as tf:
            tf.extractall(into, filter="data")
        for candidate in [into, *into.iterdir()]:
            if (candidate / "mock.yaml").exists():
                return candidate
        raise RegistryError("tarball did not contain a mock.yaml")

    def _fetch_git(self, url: str, into: Path) -> Path:
        import subprocess  # local trusted operation, not handler code

        target = into / "clone"
        subprocess.run(["git", "clone", "--depth", "1", url, str(target)], check=True,
                       capture_output=True)
        return target

    # -- io ---------------------------------------------------------------------

    @staticmethod
    def _read(url: str) -> str:
        return RegistryClient._read_bytes(url).decode()

    @staticmethod
    def _read_bytes(url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            import httpx

            resp = httpx.get(url, timeout=10, follow_redirects=True)
            resp.raise_for_status()
            return resp.content
        path = Path(parsed.path if parsed.scheme == "file" else url)
        return path.read_bytes()


def _semver_key(v: str) -> tuple:
    parts = re.split(r"[.\-+]", v)
    return tuple(int(p) if p.isdigit() else 0 for p in parts[:3])
