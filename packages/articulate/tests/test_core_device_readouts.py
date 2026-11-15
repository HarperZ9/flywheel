"""The CORE device fixture and the measurement helpers.

These tests check the instrument, not the detector: the fixture is well formed,
the interval arithmetic is right, and each readout reads the detector output it
names. They pin no recall or false-positive figure, because those are
measurements that should be free to move when a rule improves.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import core_readouts_lib as L  # noqa: E402

FIXTURE = ROOT / "tests" / "data" / "core_devices" / "passages.json"
DEVICES = {"antithesis", "tricolon", "anaphora"}


def _fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_every_passage_labels_all_three_devices():
    fx = _fixture()
    ids = [p["id"] for p in fx["passages"]]
    assert len(ids) == len(set(ids))
    for p in fx["passages"]:
        assert set(p["labels"]) == DEVICES, p["id"]
        assert p["source"], p["id"]
        if p.get("lookalike"):
            assert not any(p["labels"].values()), p["id"]


def test_each_device_has_positives_and_negatives():
    fx = _fixture()
    for d in DEVICES:
        pos = sum(p["labels"][d] for p in fx["passages"])
        assert pos >= 8 and len(fx["passages"]) - pos >= 8, d


def test_pairs_name_a_known_device_and_say_whether_it_survives():
    fx = _fixture()
    for p in fx["metamer_pairs"] + fx["isomer_pairs"]:
        assert p["device"] in DEVICES and isinstance(p["device_kept"], bool)
        assert p["a"] != p["b"], p["id"]


def test_wilson_matches_a_hand_computed_interval():
    p, lo, hi = L.wilson(84, 84)
    assert p == 1.0 and abs(lo - 0.956) < 0.001 and hi == 1.0
    assert L.wilson(0, 0) == (None, None, None)


def test_newcombe_interval_contains_the_difference():
    d, lo, hi = L.newcombe(26, 91, 2, 70)
    assert lo < d < hi and lo > 0


def test_rate_ratio_is_pooled_per_word():
    a = [(2, 100), (0, 100)]
    b = [(1, 100), (1, 100)]
    ratio, lo, hi = L.rate_ratio_boot(a, b, B=200)
    assert ratio == 1.0 and lo <= ratio <= hi


def test_readouts_read_the_detector_they_name():
    r = L.read_all("The tool is fast, simple, and private.")
    assert r["tricolon/line"] and r["tricolon/runs"]
    r = L.read_all("Every receipt names its text. Every receipt names its ruleset. "
                   "Every receipt can be replayed by anyone.")
    assert r["anaphora/runs"]
    assert set(L.READOUTS) >= {(d, i) for d in DEVICES for i in ("line", "runs")}
