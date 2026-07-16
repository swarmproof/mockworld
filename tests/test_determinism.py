"""Determinism gate G-DET (TEST-PLAN §2, DT-1..DT-8) — must be green to merge."""

from __future__ import annotations

import subprocess
import sys
import textwrap

from conftest import charge_script, digest, payments_engine, seeded_customer


def test_dt1_seed_to_identical_initial_state():
    a = payments_engine(seed=42).store.snapshot_dict("s")
    b = payments_engine(seed=42).store.snapshot_dict("s")
    assert digest(a) == digest(b)


def test_dt2_seed_to_identical_transcript():
    t1 = charge_script(payments_engine(seed=42), "s", n=20)
    t2 = charge_script(payments_engine(seed=42), "s", n=20)
    assert t1 == t2  # byte-identical incl. ids, timestamps, order


def test_seed_sensitivity():
    assert charge_script(payments_engine(seed=42), "s") != charge_script(payments_engine(seed=43), "s")


def test_dt3_reset_equals_restart():
    e = payments_engine(seed=42)
    charge_script(e, "s", n=5)          # dirty the world
    e.reset(42)                          # reset ≡ fresh run(42)
    after_reset = charge_script(e, "s", n=20)
    fresh = charge_script(payments_engine(seed=42), "s", n=20)
    assert after_reset == fresh


def test_dt4_independent_of_pythonhashseed():
    """Cross-host proxy: ids must not depend on process hash randomization (DT-4/DT-6)."""
    prog = textwrap.dedent(
        """
        from mockworld import Engine
        e = Engine.from_source('mock:payments', seed=42, faults='none')
        cid = sorted(e.store._base['customers'])[0]
        print(e.call('create_charge', {'customer_id': cid, 'amount': 100}).data['id'])
        """
    )
    outs = []
    for hashseed in ("0", "1", "12345"):
        r = subprocess.run(
            [sys.executable, "-c", prog],
            capture_output=True, text=True, env={"PYTHONHASHSEED": hashseed, "PATH": ""},
        )
        assert r.returncode == 0, r.stderr
        outs.append(r.stdout.strip())
    assert len(set(outs)) == 1, f"id varied with PYTHONHASHSEED: {outs}"


def test_dt5_store_parity_memory_vs_sqlite():
    mem = charge_script(payments_engine(seed=42, store="memory"), "s", n=20)
    sql = charge_script(payments_engine(seed=42, store="sqlite"), "s", n=20)
    assert mem == sql


def test_dt7_fault_dice_stability_under_insertion():
    """Inserting an unrelated tool call must not shift another tool's fault sequence."""
    def charge_faults(with_noise: bool):
        e = payments_engine(seed=1, faults="hostile")
        cid = seeded_customer(e)
        seq = []
        for i in range(30):
            if with_noise:
                e.call("get_customer", {"customer_id": cid})  # unrelated tool
            r = e.call("create_charge", {"customer_id": cid, "amount": 100})
            seq.append(r.success)
        return seq

    assert charge_faults(False) == charge_faults(True)


def test_dt8_handler_purity_property():
    """Same (seed, script) → same handler outputs across many amounts (entropy funnel)."""
    def run():
        e = payments_engine(seed=99, faults="none")
        cid = seeded_customer(e)
        return [e.call("create_charge", {"customer_id": cid, "amount": a}).data.get("id")
                for a in range(1, 40)]
    assert run() == run()
