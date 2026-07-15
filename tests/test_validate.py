"""Lint gate G-LINT (TEST-PLAN §6, INT-6): validate catches bad mocks."""

from __future__ import annotations

import textwrap

from mockworld.loader import list_builtin_mocks
from mockworld.validate import validate_mock


def test_all_builtin_mocks_lint_clean():
    for name in list_builtin_mocks():
        findings = validate_mock(f"mock:{name}")
        errors = [f for f in findings if f.level == "error"]
        assert not errors, f"mock:{name} has lint errors: {errors}"


def test_validate_flags_entropy_smell(tmp_path):
    mock_dir = tmp_path / "leaky"
    mock_dir.mkdir()
    (mock_dir / "mock.yaml").write_text(
        textwrap.dedent(
            """
            schema_version: "1"
            name: leaky
            description: "A mock that illegally reads the wall clock in its handler."
            state:
              widgets: {key: id, fields: {id: str}}
            tools:
              - name: make_widget
                description: "Create a widget with a nondeterministic timestamp."
                params: {name: {type: str, required: true}}
                behavior: python:handlers.make_widget
            """
        )
    )
    (mock_dir / "handlers.py").write_text(
        textwrap.dedent(
            """
            import time
            from mockworld import Result
            def make_widget(ctx, params):
                return Result.ok({"id": ctx.ids.next("w"), "at": time.time()})
            """
        )
    )
    findings = validate_mock(str(mock_dir))
    errors = [f.message for f in findings if f.level == "error"]
    assert any("entropy smell" in m for m in errors), errors


def test_validate_flags_bad_schema(tmp_path):
    mock_dir = tmp_path / "badver"
    mock_dir.mkdir()
    (mock_dir / "mock.yaml").write_text(
        'schema_version: "9"\nname: badver\ndescription: "unsupported schema version"\ntools: []\n'
    )
    findings = validate_mock(str(mock_dir))
    assert any(f.level == "error" for f in findings)
