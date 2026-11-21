"""Tests for shared negative cache and clean data distillation (harness/negative_cache.py)."""
from __future__ import annotations

import pytest

from harness.negative_cache import (
    NegativeRecord,
    build_negative_cache,
    export_distillation_corpus,
    query_dead_ends,
    verify_negative_cache,
)


def _sample_records() -> list[NegativeRecord]:
    return [
        NegativeRecord(
            record_id="bio-001",
            domain="biology",
            hypothesis="de novo binder design high confidence score predicts wet-lab binding",
            failure_mode="84 percent non-binding in wet-lab assay despite top confidence rank",
            parameters={"assay": "spr", "threshold": 0.9},
            measurement_sha256="a" * 64,
            recheck_command="crucible recheck bio-001.json",
        ),
        NegativeRecord(
            record_id="bio-002",
            domain="biology",
            hypothesis="tree ring width alone separates drought stress from root rot",
            failure_mode="confounded by canopy suppression in dense stands",
            parameters={"species": "pseudotsuga_menziesii", "cores": 42},
            measurement_sha256="b" * 64,
        ),
        NegativeRecord(
            record_id="render-001",
            domain="rendering",
            hypothesis="grid jitter temporal blend prevents thin-wall radiance leak",
            failure_mode="14 to 18 percent leak across thin wall under shifted placements",
            parameters={"jitter": 8, "sv": 2},
            measurement_sha256="c" * 64,
        ),
    ]


def test_negative_cache_seals_and_detects_tampering():
    cache = build_negative_cache(_sample_records())
    assert cache["count"] == 3
    assert cache["domains"] == ["biology", "rendering"]
    assert verify_negative_cache(cache)["verdict"] == "MATCH"

    tampered = dict(cache)
    tampered["entries"] = [dict(e) for e in cache["entries"]]
    tampered["entries"][0]["failure_mode"] = "edited"
    assert verify_negative_cache(tampered)["verdict"] == "DRIFT"


def test_query_dead_ends_catches_known_failures_and_passes_novel():
    cache = build_negative_cache(_sample_records())
    hit = query_dead_ends(
        cache,
        domain="biology",
        hypothesis="binder design high confidence score predicts wet-lab binding",
        parameters={"assay": "spr", "threshold": 0.9},
    )
    assert hit["verdict"] == "HIT"
    assert hit["hits"][0]["record_id"] == "bio-001"

    novel = query_dead_ends(
        cache,
        domain="biology",
        hypothesis="cambial electrical impedance measures sapwood moisture gradient",
    )
    assert novel["verdict"] == "NOVEL"
    assert novel["hit_count"] == 0


def test_export_distillation_corpus_balances_positives_and_verified_negatives():
    cache = build_negative_cache(_sample_records())
    positives = [
        {
            "record_id": "bio-pos-1",
            "prompt": "pair isotope delta-13C with ring width to separate drought from suppression",
            "outcome": "separated with p < 0.01 across 42 Douglas-fir cores",
            "parameters": {"species": "pseudotsuga_menziesii"},
            "measurement_sha256": "d" * 64,
        }
    ]
    corpus = export_distillation_corpus(
        domain="biology",
        positives=positives,
        negative_cache=cache,
    )
    assert corpus["positive_count"] == 1
    assert corpus["negative_count"] == 2
    assert corpus["negative_share"] == pytest.approx(0.6667, abs=1e-4)
    assert len(corpus["corpus_sha256"]) == 64

    with pytest.raises(ValueError):
        export_distillation_corpus(
            domain="biology",
            positives=[{"record_id": "bad", "prompt": "x", "outcome": "y"}],
            negative_cache=cache,
        )
