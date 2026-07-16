"""Contract-verify against a real provider's OpenAPI (ROADMAP v0.3; REQ-REC-3).

Fidelity drift is mockworld's stated risk (RESEARCH §3.5). This turns it into a
governed, testable property: compare each mock collection's shape to the matching
component schema in a provider's OpenAPI spec and report fields the mock is
missing (behind the contract) or carries that the contract doesn't (drifted).
Deterministic and offline — it reads the seeded data model, not a live API.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from .engine import Engine


@dataclass
class Finding:
    level: str  # "ok" | "drift" | "error"
    message: str


def _match_schema(collection: str, schemas: dict) -> dict | None:
    singular = collection[:-1] if collection.endswith("s") else collection
    for cand in (collection, singular, collection.capitalize(), singular.capitalize()):
        if cand in schemas:
            return schemas[cand]
    return None


def verify_against_openapi(source: str, spec_path: str, *, seed: int = 0) -> list[Finding]:
    engine = Engine.from_source(source, seed=seed, faults="none")
    with open(spec_path) as f:
        spec = yaml.safe_load(f)
    schemas = spec.get("components", {}).get("schemas", {})

    findings: list[Finding] = []
    matched = 0
    for coll, coll_def in engine.definition.state.items():
        schema = _match_schema(coll, schemas)
        if schema is None:
            continue
        matched += 1
        schema_fields = set((schema.get("properties") or {}).keys())

        sample = next(iter(engine.store._base.get(coll, {}).values()), None)
        mock_fields = set(sample.keys()) if sample else set(coll_def.fields.keys())

        missing = sorted(schema_fields - mock_fields)  # contract declares, mock lacks
        extra = sorted(mock_fields - schema_fields)      # mock has, contract omits
        for fld in missing:
            findings.append(Finding("drift", f"{coll}: missing field '{fld}' declared in the contract"))
        for fld in extra:
            findings.append(Finding("drift", f"{coll}: extra field '{fld}' not in the contract"))
        if not missing and not extra:
            findings.append(Finding("ok", f"{coll}: shape matches the contract ({len(schema_fields)} fields)"))

    if matched == 0:
        findings.append(Finding("error", "no mock collection matched a schema in the OpenAPI spec"))
    return findings
