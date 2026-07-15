"""Contract-verify gate (REQ-REC-3): fidelity drift detection against OpenAPI."""

from __future__ import annotations

import textwrap

from mockworld.verify import verify_against_openapi

MATCHING = textwrap.dedent(
    """
    openapi: 3.0.0
    info: {title: Stripe-ish}
    components:
      schemas:
        Customer:
          type: object
          properties:
            id: {type: string}
            name: {type: string}
            email: {type: string}
            balance: {type: integer}
            currency: {type: string}
    """
)

DRIFTED = textwrap.dedent(
    """
    openapi: 3.0.0
    info: {title: Stripe-ish}
    components:
      schemas:
        Customer:
          type: object
          properties:
            id: {type: string}
            name: {type: string}
            email: {type: string}
            balance: {type: integer}
            currency: {type: string}
            delinquent: {type: boolean}
    """
)


def test_detects_missing_field(tmp_path):
    spec = tmp_path / "drift.yaml"
    spec.write_text(DRIFTED)
    findings = verify_against_openapi("mock:payments", str(spec))
    drift = [f for f in findings if f.level == "drift"]
    assert any("delinquent" in f.message and "missing" in f.message for f in drift)


def test_reports_ok_when_shapes_match(tmp_path):
    spec = tmp_path / "ok.yaml"
    spec.write_text(MATCHING)
    findings = verify_against_openapi("mock:payments", str(spec))
    assert any(f.level == "ok" and "customers" in f.message for f in findings)
    assert not [f for f in findings if f.level == "drift"]


def test_error_when_nothing_matches(tmp_path):
    spec = tmp_path / "unrelated.yaml"
    spec.write_text("openapi: 3.0.0\ninfo: {title: X}\ncomponents: {schemas: {Widget: {type: object}}}\n")
    findings = verify_against_openapi("mock:payments", str(spec))
    assert any(f.level == "error" for f in findings)
