"""The joint chaos demo must stay green (launch-checklist hero artifact)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_DEMO = Path(__file__).resolve().parents[1] / "examples" / "demos" / "exactly_once_under_chaos.py"


def _load():
    spec = importlib.util.spec_from_file_location("chaos_demo", _DEMO)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exactly_once_under_chaos_all_pass():
    report = _load().run()
    assert report["all_pass"], report


def test_demo_is_deterministic():
    mod = _load()
    assert mod.run() == mod.run()  # same result every run (seedable, screenshot-worthy)
