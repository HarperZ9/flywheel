"""Falsifiers for the startup A/B gate (x-likes item 3), on synthetic numbers."""
import importlib.util
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ab():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("ab_startup", ROOT / "scripts" / "ab_startup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _runs(n, warm, rss=30e6, seed=0, jitter=0.02):
    rng = random.Random(seed)
    return [{"warm_s": warm + rng.uniform(-jitter, jitter), "cold_s": 0.4 + rng.uniform(-0.05, 0.05),
             "rss_bytes": rss + rng.uniform(-2e5, 2e5), "version_s": 0.11 + rng.uniform(-0.01, 0.01)}
            for _ in range(n)]


def test_a_clear_speedup_is_accepted():
    d = _ab().decide(_runs(20, 0.30, seed=1), _runs(20, 0.20, seed=2))
    assert d["verdict"] == "accept", d["why"]


def test_noise_is_refused():
    d = _ab().decide(_runs(20, 0.30, seed=1), _runs(20, 0.30, seed=2))
    assert d["verdict"] == "refuse" and "primary" in d["why"]


def test_a_slowdown_is_refused():
    assert _ab().decide(_runs(20, 0.30, seed=1), _runs(20, 0.35, seed=2))["verdict"] == "refuse"


def test_a_speedup_that_costs_memory_is_refused_by_the_neighbor_gate():
    d = _ab().decide(_runs(20, 0.30, seed=1), _runs(20, 0.20, rss=51e6, seed=2))
    assert d["verdict"] == "refuse" and "rss_bytes" in d["why"]


def test_the_record_is_a_hash_chain_and_an_edit_breaks_it(tmp_path):
    ab = _ab()
    rec = tmp_path / "ab.jsonl"
    ab.append_record(rec, {"label": "one", "verdict": "refuse"})
    ab.append_record(rec, {"label": "two", "verdict": "accept"})
    assert ab.verify_record(rec)
    lines = rec.read_text().splitlines()
    row = json.loads(lines[0]); row["verdict"] = "accept"; lines[0] = json.dumps(row, sort_keys=True)
    rec.write_text("\n".join(lines) + "\n")
    assert not ab.verify_record(rec)


def test_the_build_hash_changes_with_one_byte(tmp_path):
    ab = _ab()
    (tmp_path / "harness").mkdir()
    f = tmp_path / "harness" / "a.py"
    f.write_text("x = 1\n")
    before = ab.tree_sha256(tmp_path)
    f.write_text("x = 2\n")
    assert ab.tree_sha256(tmp_path) != before
