"""Load a mock directory into a runnable definition (ARCHITECTURE §4; REQ-DEF-1).

A mock is a directory: ``mock.yaml`` (authoritative) + optional ``handlers.py``,
``seed.py``, and ``fidelity.md``. Built-in mocks ship inside the package under
``mockworld/mocks/<name>/``; ``mock:<name>`` resolves there, and a filesystem
path loads a custom mock.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from .datagen import DataGen
from .determinism import DeterministicContext, IdGen
from .errors import register_error
from .schema import MockDef
from .state import Snapshot

_BUILTIN_DIR = Path(__file__).parent / "mocks"


def mockworld_home() -> Path:
    """Where registry-installed mocks live (override with ``MOCKWORLD_HOME``)."""
    return Path(os.environ.get("MOCKWORLD_HOME", str(Path.home() / ".mockworld")))


def installed_dir() -> Path:
    return mockworld_home() / "mocks"


@dataclass
class SeedCtx:
    """Context passed to a mock's ``seed.generate(ctx)`` for base-dataset creation.

    ``shared`` carries a world-level identity pool (REQ-WORLD-1) when a mock runs
    inside a composed world — e.g. ``shared["customers"]`` is the common customer
    list so payments, crm, and email all reference the same ids. ``None`` for a
    standalone mock.
    """

    rng: Any
    ids: IdGen
    fake: DataGen
    shared: dict[str, Any] | None = None


@dataclass
class LoadedMock:
    definition: MockDef
    handlers: ModuleType | None
    seed_module: ModuleType | None
    path: Path

    def generate_base(
        self, dctx: DeterministicContext, shared: dict[str, Any] | None = None
    ) -> Snapshot:
        """Produce the seeded base dataset (REQ-STATE-2). Pure function of the seed."""
        seed_def = self.definition.seed
        seed_ctx = SeedCtx(
            rng=dctx.seed_rng(),
            ids=dctx.ids_for("__seed__", 0),
            fake=DataGen(dctx.seed_rng()),
            shared=shared,
        )
        if seed_def.generator.startswith("python:") and self.seed_module is not None:
            fn_name = seed_def.generator.split(".", 1)[-1]
            fn = getattr(self.seed_module, fn_name, None)
            if fn is None:
                raise AttributeError(f"seed generator {seed_def.generator!r} not found")
            return fn(seed_ctx, self.definition)
        return self._builtin_seed(seed_ctx)

    def _builtin_seed(self, ctx: SeedCtx) -> Snapshot:
        """Generic type-driven generation for mocks without a custom seed.py."""
        snapshot: Snapshot = {}
        for coll_name, coll in self.definition.state.items():
            n = self.definition.seed.volume.get(coll_name, 0)
            entities: dict[str, dict] = {}
            for _ in range(n):
                entity: dict[str, Any] = {}
                for fname, ftype in coll.fields.items():
                    entity[fname] = self._gen_field(ctx, fname, ftype)
                key = str(entity.get(coll.key) or ctx.ids.next(coll_name[:3]))
                entity[coll.key] = key
                entities[key] = entity
            snapshot[coll_name] = entities
        return snapshot

    @staticmethod
    def _gen_field(ctx: SeedCtx, name: str, ftype: str) -> Any:
        if "email" in name:
            return ctx.fake.email()
        if "name" in name:
            return ctx.fake.name()
        if ftype == "int":
            return ctx.rng.randint(0, 100_000)
        if ftype == "float":
            return round(ctx.rng.uniform(0, 1000), 2)
        if ftype == "bool":
            return ctx.rng.choice([True, False])
        return ctx.fake.word()


def _import_module(path: Path, mod_name: str) -> ModuleType | None:
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_source(source: str) -> Path:
    """Resolve ``mock:<name>`` to a built-in or registry-installed dir; else a path.

    Built-ins take precedence over installed mocks of the same name.
    """
    if source.startswith("mock:"):
        name = source.split(":", 1)[1]
        builtin = _BUILTIN_DIR / name
        if builtin.is_dir():
            return builtin
        installed = installed_dir() / name
        if installed.is_dir():
            return installed
        return builtin  # nonexistent → callers raise a helpful FileNotFoundError
    return Path(source)


def load_mock(source: str) -> LoadedMock:
    path = resolve_source(source)
    if not path.is_dir():
        raise FileNotFoundError(f"mock directory not found: {path}")

    yaml_path = path / "mock.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"mock.yaml not found in {path}")
    with open(yaml_path) as f:
        raw = yaml.safe_load(f)
    definition = MockDef.model_validate(raw)

    for name, template in definition.errors.items():
        register_error(name, template)

    safe = definition.name.replace("-", "_")
    handlers = _import_module(path / "handlers.py", f"mockworld_mock_{safe}_handlers")
    seed_module = _import_module(path / "seed.py", f"mockworld_mock_{safe}_seed")

    return LoadedMock(definition=definition, handlers=handlers, seed_module=seed_module, path=path)


def _list_mocks_in(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if p.is_dir() and (p / "mock.yaml").exists())


def list_builtin_mocks() -> list[str]:
    return _list_mocks_in(_BUILTIN_DIR)


def list_installed_mocks() -> list[str]:
    """Registry-installed mocks not shadowed by a built-in of the same name."""
    builtins = set(list_builtin_mocks())
    return [n for n in _list_mocks_in(installed_dir()) if n not in builtins]
