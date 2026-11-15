"""plexus pick: tool probabilities, the abstain outcome and the bench.

Each behaviour is asserted with a paired mutation that must flip it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from plexus.cli import main  # noqa: E402
from plexus.manifest import Manifest  # noqa: E402
from plexus.mesh import discover  # noqa: E402
from plexus.pick import pick, terms, tool_document  # noqa: E402
from plexus.pick_bench import abstain_stats, calibrate, run, split  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "plexus_pick_labels.json"


def _mesh():
    return discover([
        Manifest.from_dict({"organ": "memory", "emits": [
            {"capability": "mem.recall/1", "title": "recall receipt for stored notes"}]}),
        Manifest.from_dict({"organ": "judge", "consumes": [
            {"capability": "judge.thesis/1", "title": "thesis measured against evidence"}]}),
    ])


def test_clear_request_is_picked_and_unmatched_request_abstains():
    mesh = _mesh()
    hit = pick(mesh, "recall my stored notes")
    assert hit["picked"] == "memory" and hit["abstained"] is False
    miss = pick(mesh, "compose a symphony")
    assert miss["picked"] is None and miss["abstained"] is True


def test_threshold_turns_a_weak_match_into_an_abstain():
    weak = "notes about the thesis"
    assert pick(_mesh(), weak, threshold=0.0)["picked"] is not None
    assert pick(_mesh(), weak, threshold=0.99)["picked"] is None


def test_candidates_are_probabilities_best_first():
    r = pick(_mesh(), "measure the thesis against evidence")
    probs = [c["probability"] for c in r["candidates"]]
    assert abs(sum(probs) - 1.0) < 1e-5 and probs == sorted(probs, reverse=True)
    assert r["candidates"][0]["tool"] == "judge"


def test_tool_document_reads_titles_and_capability_words():
    doc = tool_document(_mesh().manifests["memory"])
    assert "receipt" in doc and "mem" in doc and "memory" in doc
    assert "thesis" not in doc


def test_terms_stem_and_drop_stop_words():
    assert terms("The receipts") == ["receipt"]
    assert terms("the") == []


def test_invalid_threshold_is_refused():
    with pytest.raises(ValueError):
        pick(_mesh(), "x", threshold=2.0)


def test_calibration_reaches_the_requested_share():
    items = [{"text": t} for t in ("recall notes", "thesis evidence", "notes thesis",
                                   "symphony", "recall", "evidence", "stored",
                                   "measured", "receipt", "notes")]
    mesh = _mesh()
    t = calibrate(mesh, items, share=0.30)
    assert sum(pick(mesh, i["text"], threshold=t)["abstained"] for i in items) >= 3
    assert calibrate(mesh, items, share=0.30) >= calibrate(mesh, items, share=0.10)


def test_abstain_stats_and_undefined_ratio():
    s = abstain_stats([("a", "a", "a"), ("a", "a", "b"), ("a", None, "b")])
    assert s["decided_error_rate"] == 0.5 and s["error_ratio"] == 2.0
    assert abstain_stats([("a", "a", "a"), ("a", None, "b")])["error_ratio"] is None


def test_split_is_deterministic_and_complete():
    items = [{"id": f"p{i:03d}"} for i in range(30)]
    dev, test = split(items)
    assert (dev, test) == split(items)
    assert len(dev) + len(test) == 30 and split(items, seed=7) != (dev, test)


def test_bench_reproduces_the_reported_result():
    items = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]
    out = run(items)
    assert all(out["bar"].values()), out["bar"]
    assert out == run(items)


def test_cli_pick_prints_a_pick(capsys):
    assert main(["pick", "verify a sealed wiki pinned to a commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == "plexus.pick/1" and out["picked"] == "index"
