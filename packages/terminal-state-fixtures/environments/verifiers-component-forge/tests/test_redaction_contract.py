"""Oracle soundness for the redaction-contract family.

The family is deliberately small and synthetic: raw values are fake markers,
but the contract is the real one a public-safe provenance fixture needs to
test. The scorer rewards terminal JSON state, not claims about redaction.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verifiers_component_forge.families import redaction_contract as rc
from verifiers_component_forge.harness import runner

DATA = (
    Path(__file__).resolve().parents[1]
    / "verifiers_component_forge"
    / "data"
    / "redaction_contract.json"
)


def _frozen() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_reference_redacts_raw_secret_values_and_preserves_metadata():
    record = {
        "secrets": [
            {
                "name": "AUTH_TOKEN",
                "value": "FAKE_SECRET_DO_NOT_USE_LOOP29_AUTH",
                "source": "env:AUTH_TOKEN",
            }
        ],
        "config": {
            "endpoint": "https://example.invalid/eval",
            "headers": {
                "Authorization": "Bearer FAKE_SECRET_DO_NOT_USE_LOOP29_AUTH",
                "X-Trace": "trace-public-001",
            },
        },
        "manifest": {"sha256": "0" * 64, "path_label": "artifact:stdout"},
    }

    redacted = rc.reference_redact(record)

    assert redacted["redaction_policy"] == rc.POLICY
    assert redacted["config"]["endpoint"] == "https://example.invalid/eval"
    assert redacted["config"]["headers"]["X-Trace"] == "trace-public-001"
    assert (
        redacted["config"]["headers"]["Authorization"] == "Bearer <redacted:AUTH_TOKEN>"
    )
    assert redacted["secrets"][0]["value"] == "<redacted:AUTH_TOKEN>"
    assert "FAKE_SECRET_DO_NOT_USE_LOOP29_AUTH" not in json.dumps(redacted)


def test_reference_uses_longest_secret_first_for_overlapping_values():
    record = {
        "secrets": [
            {"name": "SHORT", "value": "FAKE_SECRET_DO_NOT_USE_LOOP29_TOKEN"},
            {"name": "LONG", "value": "FAKE_SECRET_DO_NOT_USE_LOOP29_TOKEN_EXTRA"},
        ],
        "stdout": "got FAKE_SECRET_DO_NOT_USE_LOOP29_TOKEN_EXTRA",
    }

    redacted = rc.reference_redact(record)

    assert redacted["stdout"] == "got <redacted:LONG>"


def test_secret_ref_objects_survive_without_becoming_raw_values():
    record = {
        "secrets": [{"name": "API_KEY", "value": "FAKE_SECRET_DO_NOT_USE_LOOP29_API"}],
        "config": {"api_key": {"secret_ref": "API_KEY"}},
        "stderr": "using secret_ref API_KEY",
    }

    redacted = rc.reference_redact(record)

    assert redacted["config"]["api_key"] == {"secret_ref": "API_KEY"}
    assert redacted["stderr"] == "using secret_ref API_KEY"
    assert "FAKE_SECRET_DO_NOT_USE_LOOP29_API" not in json.dumps(redacted)


def test_frozen_file_matches_regeneration():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generation"))
    import generate

    regenerated = generate._dumps(generate.build_redaction_contract())
    assert regenerated == DATA.read_text(encoding="utf-8")


def test_expected_outputs_never_contain_raw_synthetic_secrets():
    data = _frozen()
    assert len(data) == 4
    for entry in data.values():
        for row in entry["fixtures"] + entry["worked"]:
            expected = json.dumps(row["expect"], sort_keys=True)
            for raw in _declared_raw_secret_values(row["record"]):
                assert raw not in expected
        assert len(entry["fixtures"]) >= 5


def _canonical_record_expect_pair(row: dict) -> str:
    return json.dumps(
        {"record": row["record"], "expect": row["expect"]},
        sort_keys=True,
        ensure_ascii=True,
    )


def _declared_raw_secret_values(record: dict) -> list[str]:
    rows = record.get("secrets") or []
    values = []
    for item in rows:
        if (
            isinstance(item, dict)
            and isinstance(item.get("value"), str)
            and item["value"]
        ):
            values.append(item["value"])
    return values


def test_worked_examples_are_canonically_disjoint_from_scored_pairs():
    for variant in rc.all_variants():
        scored_pairs = {
            _canonical_record_expect_pair(
                {"record": row["record"], "expect": rc.reference_redact(row["record"])}
            )
            for row in rc.fixtures_for(variant)
        }
        worked_pairs = {
            _canonical_record_expect_pair(row) for row in rc.worked_for(variant)
        }

        assert worked_pairs
        assert worked_pairs.isdisjoint(scored_pairs)


def test_generator_safety_check_derives_declared_raw_secret_values():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generation"))
    import generate

    unsafe = {
        "unsafe-variant": {
            "fixtures": [
                {
                    "cell": "raw-value-without-standard-prefix",
                    "record": {
                        "secrets": [{"name": "TOKEN", "value": "declared-raw-token"}],
                    },
                    "expect": {"stdout": "declared-raw-token"},
                }
            ],
            "worked": [],
        }
    }

    with pytest.raises(ValueError, match="declared raw secret"):
        generate.assert_redaction_expected_safe(unsafe)


REFERENCE_MODULE = """
from copy import deepcopy

POLICY = "redaction-contract/1"

def _secrets(record):
    rows = record.get("secrets") or []
    return sorted(
        [(str(r.get("name")), str(r.get("value"))) for r in rows if r.get("value")],
        key=lambda item: len(item[1]),
        reverse=True,
    )

def _walk(value, secrets):
    if isinstance(value, str):
        text = value
        for name, raw in secrets:
            text = text.replace(raw, f"<redacted:{name}>")
        return text
    if isinstance(value, list):
        return [_walk(v, secrets) for v in value]
    if isinstance(value, dict):
        return {str(k): _walk(v, secrets) for k, v in value.items()}
    return value

def redact_record(record):
    out = _walk(deepcopy(record), _secrets(record))
    out["redaction_policy"] = POLICY
    return out
"""


LEAKY_MODULE = """
def redact_record(record):
    return record
"""


def _score_module(module_source: str, entry: dict) -> float:
    result = asyncio.run(
        runner.run_child(
            "child_driver_redaction.py",
            module_source,
            [p["record"] for p in entry["fixtures"]],
            wall_clock=60.0,
        )
    )
    assert result.ok, (result.failure, result.stderr_tail)
    return runner.match_fraction(
        result.payload["results"],
        [p["expect"] for p in entry["fixtures"]],
    )


def test_reference_scores_full_marks_and_leaky_module_fails():
    frozen = _frozen()
    for entry in frozen.values():
        assert _score_module(REFERENCE_MODULE, entry) == 1.0
        assert _score_module(LEAKY_MODULE, entry) == 0.0
