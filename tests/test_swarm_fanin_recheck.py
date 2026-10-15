"""Falsifiers for the offline swarm fan-in recheck and quorum semantics at 512 children."""
import copy
import importlib.util
from pathlib import Path

import pytest

from harness.subagent_fanin import recheck_swarm_receipt
from harness.subagent_roles import MAX_CHILDREN, quorum
from harness.subagent_store import load_swarm_receipt, swarm_dir

ROOT = Path(__file__).resolve().parent.parent


def _measure():
    spec = importlib.util.spec_from_file_location("measure_swarm_fanin",
                                                  ROOT / "scripts" / "measure_swarm_fanin.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sealed(tmp_path, n, policy="majority"):
    m = _measure()
    rec = m.synthetic_rec(n, policy)
    from harness.subagent_fanin import finalize_swarm
    finalize_swarm(m.FakeRunner(tmp_path), rec)
    return load_swarm_receipt(swarm_dir(tmp_path, rec["swarm_id"]) / "swarm.json")


@pytest.mark.parametrize("n", [8, 64, 512])
def test_a_fresh_seal_rechecks_as_match(tmp_path, n):
    r = recheck_swarm_receipt(_sealed(tmp_path, n))
    assert r == {"verdict": "MATCH", "drift": [], "children": n}


def test_flipping_one_childs_accepted_flag_is_drift(tmp_path):
    receipt = _sealed(tmp_path, 512)
    bad = copy.deepcopy(receipt)
    bad["children"][300]["accepted"] = not bad["children"][300]["accepted"]
    r = recheck_swarm_receipt(bad)
    assert r["verdict"] == "DRIFT"
    assert {"verified.accepted", "swarm_cert.children", "swarm_cert.cert_sha256"} <= set(r["drift"])


def test_changing_one_chain_head_is_drift(tmp_path):
    bad = _sealed(tmp_path, 512)
    bad["children"][511]["verdict_chain_head"] = "0" * 64
    r = recheck_swarm_receipt(bad)
    assert r["verdict"] == "DRIFT" and "swarm_cert.cert_sha256" in r["drift"]


def test_an_edited_verdict_is_drift(tmp_path):
    bad = _sealed(tmp_path, 64)
    bad["verified"]["verdict"] = "satisfied" if bad["verified"]["verdict"] != "satisfied" \
        else "unsatisfied"
    assert recheck_swarm_receipt(bad)["drift"] == ["verified.verdict"]


def test_not_a_swarm_receipt_is_unverifiable():
    assert recheck_swarm_receipt({"schema": "other"})["verdict"] == "UNVERIFIABLE"


def test_quorum_rules_mean_what_they_say_at_512():
    assert quorum("any", 1, 512) == {"required": 1, "completed": 1, "total": 512,
                                     "verdict": "satisfied"}
    assert quorum("any", 0, 512)["verdict"] == "unsatisfied"
    assert quorum("majority", 256, 512)["verdict"] == "unsatisfied"
    assert quorum("majority", 257, 512)["verdict"] == "satisfied"
    assert quorum("all", 511, 512)["verdict"] == "unsatisfied"
    assert quorum("all", 512, 512)["verdict"] == "satisfied"


def test_the_cap_stays_at_8_until_children_run_under_a_limit():
    # Measured: recheck cost is flat to 512 children, but every child is a
    # process launched at once; raising the cap waits for a running limit.
    assert MAX_CHILDREN == 8
