"""DX gates: pytest fixture, `mockworld new` scaffold, mock:hello example."""

from __future__ import annotations

from mockworld import Engine
from mockworld.scaffold import new_mock
from mockworld.validate import validate_mock


# --- the pytest fixture itself (dogfooding the adoption channel) --------------
def test_mockworld_fixture_boots_a_seeded_engine(mockworld):
    pay = mockworld.start("mock:payments", seed=7, faults="none")
    cust = pay.call("create_customer", {"name": "A", "balance": 10_000}).data
    charge = pay.call("create_charge", {"customer_id": cust["id"], "amount": 2_500})
    assert charge.success and charge.data["status"] == "succeeded"


def test_fixture_engines_are_isolated_and_deterministic(mockworld):
    a = mockworld.start("mock:payments", seed=7, faults="none")
    b = mockworld.start("mock:payments", seed=7, faults="none")
    # independent engines; same seed → same first minted id, separate state
    ida = a.call("create_customer", {"name": "x", "balance": 1}).data["id"]
    idb = b.call("create_customer", {"name": "x", "balance": 1}).data["id"]
    assert ida == idb  # deterministic
    assert a.call("get_customer", {"customer_id": idb}).data is not None  # each has its own copy


def test_fixture_world(mockworld):
    from pathlib import Path

    w = mockworld.world(
        "world:" + str(Path(__file__).resolve().parents[1] / "examples" / "worlds" / "ecommerce.yaml"),
        seed=42, faults="none",
    )
    assert any(t.name == "payments_create_charge" for t in w.definition.tools)


# --- `mockworld new` scaffold -------------------------------------------------
def test_new_mock_lints_and_runs(tmp_path):
    out = new_mock("acme", out_dir=str(tmp_path / "acme"))
    assert not [f for f in validate_mock(str(out)) if f.level == "error"]
    e = Engine.from_source(str(out), seed=1, faults="none")
    created = e.call("create_item", {"label": "widget"})
    assert created.success
    assert e.call("get_item", {"id": created.data["id"]}).success
    assert e.call("list_items", {}).data["count"] == 11  # 10 seeded + 1


def test_new_mock_refuses_nonempty_dir(tmp_path):
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "x").write_text("y")
    import pytest

    with pytest.raises(FileExistsError):
        new_mock("taken", out_dir=str(tmp_path / "taken"))


# --- the shipped mock:hello example ------------------------------------------
def test_hello_example_lints_and_runs():
    assert not [f for f in validate_mock("mock:hello") if f.level == "error"]
    e = Engine.from_source("mock:hello", seed=1, faults="none")
    g = e.call("say_hello", {"name": "Ada"})
    assert g.success and g.data["message"] == "Hello, Ada!"
    assert e.call("list_greetings", {}).data["count"] == 6  # 5 seeded + 1
