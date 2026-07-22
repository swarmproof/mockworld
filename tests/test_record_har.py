"""HAR record-mode gate (REQ-REC-1 F2): traffic capture → runnable scaffold."""

from __future__ import annotations

import json

import pytest
from mockworld import Engine
from mockworld.record import from_har
from mockworld.validate import validate_mock

HAR = {
    "log": {
        "entries": [
            {
                "request": {"method": "GET", "url": "https://api.x.com/v1/orders?status=open&api_key=SECRET"},
                "response": {"status": 200, "content": {"mimeType": "application/json",
                    "text": json.dumps({"data": [{"id": "ord_1", "total": 4200, "status": "open", "paid": False}]})}},
            },
            {
                "request": {"method": "GET", "url": "https://api.x.com/v1/orders/ord_1"},
                "response": {"status": 200, "content": {"mimeType": "application/json",
                    "text": json.dumps({"id": "ord_1", "total": 4200, "status": "open", "paid": False})}},
            },
            {
                "request": {"method": "POST", "url": "https://api.x.com/v1/orders",
                            "postData": {"text": json.dumps({"total": 999, "password": "x"})}},
                "response": {"status": 201, "content": {"mimeType": "application/json",
                    "text": json.dumps({"id": "ord_2", "total": 999, "status": "open", "paid": False})}},
            },
            {
                "request": {"method": "POST", "url": "https://api.x.com/v1/orders/ord_1/refund"},
                "response": {"status": 200, "content": {"mimeType": "application/json",
                    "text": json.dumps({"refunded": True})}},
            },
        ]
    }
}


@pytest.fixture
def scaffold(tmp_path):
    har = tmp_path / "traffic.har"
    har.write_text(json.dumps(HAR))
    return from_har(str(har), name="orders", out_dir=str(tmp_path / "orders_mock"))


def test_har_scaffold_lints_and_runs(scaffold):
    assert not [f for f in validate_mock(str(scaffold)) if f.level == "error"]
    e = Engine.from_source(str(scaffold), seed=1, faults="none")
    created = e.call("create_order", {"total": 500})
    assert created.success
    assert e.call("get_order", {"id": created.data["id"]}).success


def test_har_templatizes_ids_and_maps_crud(scaffold):
    e = Engine.from_source(str(scaffold), seed=1, faults="none")
    behaviors = {t.name: t.behavior for t in e.definition.tools}
    # /orders/ord_1 and /orders/{id} collapsed to one read tool
    assert behaviors.get("get_order") == "crud:read"
    assert behaviors.get("list_orders") == "crud:list"
    assert behaviors.get("create_order") == "crud:create"
    # the custom /orders/{id}/refund action is a stub, not miscategorized
    assert any(b.startswith("python:") for n, b in behaviors.items() if "refund" in n)


def test_har_infers_fields_and_scrubs_secrets(scaffold):
    e = Engine.from_source(str(scaffold), seed=1, faults="none")
    assert set(e.definition.state["orders"].fields) >= {"id", "total", "status", "paid"}
    all_params = {p for t in e.definition.tools for p in t.params}
    assert "api_key" not in all_params and "password" not in all_params
