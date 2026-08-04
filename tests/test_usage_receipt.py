"""Tests for the usage-metering receipt: seal round-trip, tamper refusal, the
field contracts (token arithmetic, source label, string-typed cost), and the two
honesty invariants -- no float anywhere in the body, and an unpriced local
endpoint records an empty amount plus a note rather than an invented dollar."""
import json

from harness.usage_receipt import (
    SCHEMA,
    build_usage_receipt,
    verify_usage_receipt,
    emit_usage_receipt,
)

_PRICED_COST = {
    "amount": "0.000450",
    "currency": "USD",
    "per_million_input": "0.15",
    "per_million_output": "0.60",
    "note": "dollar amount is a table lookup at listed per-million prices, "
            "not a provider-billed figure",
}
_LOCAL_COST = {
    "amount": "",
    "currency": "",
    "per_million_input": "",
    "per_million_output": "",
    "note": "no per-token price for a local endpoint",
}


def _priced(**over):
    kw = dict(
        run_id="u-priced", endpoint="openai", model_ref="openai:gpt-4o-mini",
        tokens={"prompt": 1000, "completion": 500, "total": 1500},
        cost=_PRICED_COST, source="provider_reported",
        started_utc="2026-08-04T00:00:00+00:00",
        finished_utc="2026-08-04T00:00:01+00:00",
        prev_receipt_sha256="a" * 64,
    )
    kw.update(over)
    return build_usage_receipt(**kw)


def _floats_in(obj):
    """Any float anywhere in the receipt body is a discipline violation."""
    if isinstance(obj, float):
        return True
    if isinstance(obj, dict):
        return any(_floats_in(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_floats_in(v) for v in obj)
    return False


def _abs_path_in(obj):
    """Any Windows drive path or leading-slash absolute path in a string value
    means the receipt leaked a host path and is no longer portable."""
    import re
    drive = re.compile(r"[A-Za-z]:[\\/]")
    if isinstance(obj, str):
        return bool(drive.search(obj)) or obj.startswith("/") or "\\" in obj
    if isinstance(obj, dict):
        return any(_abs_path_in(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_abs_path_in(v) for v in obj)
    return False


def test_seal_round_trip_is_match():
    r = _priced()
    v = verify_usage_receipt(r)
    assert v["verdict"] == "MATCH"
    assert v["source"] == "provider_reported"
    assert r["schema"] == SCHEMA


def test_tampering_a_token_count_is_tampered():
    r = _priced()
    bad = json.loads(json.dumps(r))
    bad["tokens"]["prompt"] = "999999"  # the seal no longer covers this body
    v = verify_usage_receipt(bad)
    assert v["verdict"] == "TAMPERED"
    assert v["failure_class"] == "SEAL_MISMATCH"


def test_total_not_equal_prompt_plus_completion_is_field_contract_violation():
    # Built with a wrong total, so the seal PASSES over the bad body and the
    # arithmetic contract is what must catch it -- not the seal.
    r = _priced(tokens={"prompt": 1000, "completion": 500, "total": 1400})
    v = verify_usage_receipt(r)
    assert v["verdict"] == "UNVERIFIABLE"
    assert v["failure_class"] == "FIELD_CONTRACT_VIOLATION"
    assert "total" in v["detail"]


def test_unknown_source_label_is_field_contract_violation():
    r = _priced(source="vibes")
    v = verify_usage_receipt(r)
    assert v["verdict"] == "UNVERIFIABLE"
    assert v["failure_class"] == "FIELD_CONTRACT_VIOLATION"
    assert "source" in v["detail"]


def test_no_float_and_no_absolute_path_in_the_body():
    r = _priced()
    assert not _floats_in(r), "a float leaked into the sealed body"
    assert not _abs_path_in(r), "a host path leaked into the receipt"
    # the money and token fields are strings, never numbers
    assert isinstance(r["cost"]["amount"], str)
    assert all(isinstance(r["tokens"][k], str) for k in ("prompt", "completion", "total"))


def test_unpriced_local_carries_empty_amount_and_a_note():
    r = build_usage_receipt(
        run_id="u-local", endpoint="ollama", model_ref="ollama",
        tokens={"prompt": 40, "completion": 20, "total": 60},
        cost=_LOCAL_COST, source="unpriced_local",
        started_utc="x", finished_utc="y")
    v = verify_usage_receipt(r)
    assert v["verdict"] == "MATCH"
    assert r["source"] == "unpriced_local"
    assert r["cost"]["amount"] == ""            # no invented dollars
    assert r["cost"]["note"].strip() != ""      # the honest reason is recorded


def test_a_foreign_schema_is_refused_before_any_field_is_trusted():
    assert verify_usage_receipt(None)["verdict"] == "UNVERIFIABLE"
    assert verify_usage_receipt({"schema": "not-ours"})["failure_class"] == "MALFORMED"


def test_cost_fields_must_all_be_strings():
    r = _priced()
    bad = json.loads(json.dumps(r))
    bad["cost"]["amount"] = 0.000450          # a float smuggled back in
    from harness.usage_receipt import _seal_receipt
    _seal_receipt(bad)                        # re-seal so the seal passes
    v = verify_usage_receipt(bad)
    assert v["verdict"] == "UNVERIFIABLE"
    assert v["failure_class"] == "FIELD_CONTRACT_VIOLATION"


def test_emit_writes_a_bare_filename_that_reverifies(tmp_path):
    r = _priced()
    path = emit_usage_receipt(r, tmp_path / "usage")
    assert path is not None
    assert path.name.startswith("usage-receipt-") and path.name.endswith(".json")
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert verify_usage_receipt(reloaded)["verdict"] == "MATCH"
