"""Incident case: the admitted-facts input to the compiler. Public-safe
fields only; the case binds itself to one journey head."""
import pytest

from harness.incident_case import new_incident_case

FACT = {"fact_id": "fact_" + "a" * 8, "statement": "the gate refused"}


def _case(**over):
    kwargs = dict(
        case_id="case_" + "a" * 8,
        journey_ref="jrn_" + "a" * 32,
        event_head_sha256="a" * 64,
        source_refs=[FACT],
        failure={"summary": "check failed on the submitted object"},
        created_at="2026-08-22T12:00:00Z",
    )
    kwargs.update(over)
    return new_incident_case(**kwargs)


def test_case_schema_and_sha():
    case = _case()
    assert case["schema"] == "flywheel.incident-case/v1"
    assert case["case_sha256"]


def test_case_is_deterministic():
    assert _case() == _case()


def test_raw_paths_and_secret_keys_are_refused():
    with pytest.raises(ValueError):
        _case(failure={"summary": "x", "log_path": "C:\\dev\\secrets.txt"})
    with pytest.raises(ValueError):
        _case(failure={"summary": "x", "api_key": "sk-no"})


def test_unknown_top_level_fields_are_refused():
    # The constructor's signature is the allowlist: an unknown field
    # cannot even be passed, let alone stored.
    with pytest.raises(TypeError):
        _case(command="rm -rf /")
