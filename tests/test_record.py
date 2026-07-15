"""Record-mode gate (REQ-REC-*): OpenAPI → runnable scaffold."""

from __future__ import annotations

import textwrap

import pytest
from mockworld import Engine
from mockworld.record import from_openapi
from mockworld.validate import validate_mock

SPEC = textwrap.dedent(
    """
    openapi: 3.0.0
    info: {title: Pet Store, description: sample}
    paths:
      /pets:
        get: {operationId: listPets, summary: List pets}
        post:
          operationId: createPet
          summary: Create a pet
          requestBody:
            content:
              application/json:
                schema:
                  type: object
                  required: [name]
                  properties:
                    name: {type: string}
                    age: {type: integer}
                    api_key: {type: string}
      /pets/{petId}:
        get:
          operationId: getPet
          summary: Get a pet
          parameters: [{name: petId, in: path, required: true, schema: {type: string}}]
        delete:
          operationId: deletePet
          summary: Delete a pet
          parameters: [{name: petId, in: path, required: true, schema: {type: string}}]
      /pets/{petId}/adopt:
        post:
          operationId: adoptPet
          summary: Adopt a pet
          parameters: [{name: petId, in: path, required: true, schema: {type: string}}]
    components:
      schemas:
        Pet: {type: object, properties: {id: {type: string}, name: {type: string}, age: {type: integer}}}
    """
)


@pytest.fixture
def scaffold(tmp_path):
    spec = tmp_path / "petstore.yaml"
    spec.write_text(SPEC)
    return from_openapi(str(spec), out_dir=str(tmp_path / "petstore_mock"))


def test_scaffold_lints_clean_and_runs(scaffold):
    assert not [f for f in validate_mock(str(scaffold)) if f.level == "error"]
    e = Engine.from_source(str(scaffold), seed=1, faults="none")
    created = e.call("create_pet", {"name": "Rex", "age": 3})
    assert created.success
    assert e.call("get_pet", {"pet_id": created.data["id"]}).data["name"] == "Rex"


def test_crud_vs_custom_action_mapping(scaffold):
    e = Engine.from_source(str(scaffold), seed=1, faults="none")
    behaviors = {t.name: t.behavior for t in e.definition.tools}
    assert behaviors["list_pets"] == "crud:list"
    assert behaviors["create_pet"] == "crud:create"
    assert behaviors["get_pet"] == "crud:read"
    assert behaviors["delete_pet"] == "crud:delete"
    # sub-resource action is a handler stub, not miscategorized as CRUD
    assert behaviors["adopt_pet"].startswith("python:")
    assert e.call("adopt_pet", {"pet_id": "x"}).err.code == "not_implemented"


def test_secret_fields_are_scrubbed(scaffold):
    e = Engine.from_source(str(scaffold), seed=1, faults="none")
    assert "api_key" not in e.definition.tool("create_pet").params


def test_seed_has_no_key_collisions(scaffold):
    e = Engine.from_source(str(scaffold), seed=1, faults="none")
    assert e.call("list_pets", {}).data["count"] == 20  # full seeded volume, unique keys
