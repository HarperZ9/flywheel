import json
import io
from pathlib import Path

from harness.outcome_bulletin_cli import main
from tests.test_outcome_bulletin import INDEX_OUTCOME


def _write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_cli_preview_prints_reviewable_post_payload(tmp_path, capsys):
    """Breaking CLI preview would leave the operator approving hidden input."""
    outcome = _write(tmp_path / "outcome.json", INDEX_OUTCOME)

    assert main(["preview", "--outcome", str(outcome)]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["schema"] == "flywheel.outcome-bulletin-preview/v1"
    assert result["post"]["room"] == "findings"
    assert "Index 2.11.0 release" in result["post"]["body"]


def test_cli_grant_request_prints_exact_lane_call_operation(tmp_path, capsys):
    """Root needs the exact private grant request, not hand-transcribed args."""
    outcome = _write(tmp_path / "outcome.json", INDEX_OUTCOME)

    code = main([
        "grant-request", "--outcome", str(outcome),
        "--journey-ref", "jrn_" + "a" * 32,
        "--expected-event-head", "b" * 64,
        "--client-request-id", "index-outcome-20260907",
    ])
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["schema"] == "flywheel.gateway-operation/v1"
    assert result["operation"]["name"] == "bulletin"
    assert result["operation"]["tool"] == "board_write_post"
    assert result["operation"]["governance_tier"] == "T2"
    assert result["operation"]["credential_refs"] == []
    assert set(result) == {
        "schema", "journey_ref", "expected_event_head",
        "client_request_id", "operation",
    }


def test_cli_publish_envelope_prints_final_approved_lane_call(tmp_path, capsys):
    """After approval, root should not hand-flatten the gateway envelope."""
    outcome = _write(tmp_path / "outcome.json", INDEX_OUTCOME)

    code = main([
        "publish-envelope", "--outcome", str(outcome),
        "--journey-ref", "jrn_" + "a" * 32,
        "--expected-event-head", "b" * 64,
        "--client-request-id", "index-outcome-20260907",
        "--grant-ref", "gnt_" + "c" * 32,
    ])
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["schema"] == "flywheel.gateway-operation/v1"
    assert result["grant_ref"] == "gnt_" + "c" * 32
    assert result["name"] == "bulletin"
    assert result["tool"] == "board_write_post"
    assert result["args"]["room"] == "findings"
    assert result["credential_refs"] == []


def test_cli_can_bind_reviewed_bulletin_credential_ref(tmp_path, capsys):
    outcome = _write(tmp_path / "outcome.json", INDEX_OUTCOME)
    ref = "cred_" + "a" * 32

    assert main([
        "grant-request", "--outcome", str(outcome),
        "--journey-ref", "jrn_" + "a" * 32,
        "--expected-event-head", "b" * 64,
        "--client-request-id", "index-outcome-20260907",
        "--credential-ref", ref,
    ]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["operation"]["credential_refs"] == [ref]


def test_cli_invalid_input_is_fixed_json_without_path_echo(tmp_path, capsys):
    """A malformed public draft must not echo the local filename or contents."""
    outcome = _write(tmp_path / "private-outcome.json", {
        **INDEX_OUTCOME,
        "checked": ["C:/dev/private/state.json"],
    })

    assert main(["preview", "--outcome", str(outcome)]) == 2
    result = json.loads(capsys.readouterr().out)

    assert result["error"]["code"] == "UNSAFE_PUBLIC_OUTCOME"
    assert "private-outcome" not in json.dumps(result)
    assert "C:/dev" not in json.dumps(result)


def test_cli_bounds_file_read_before_allocating_input(monkeypatch, capsys):
    class BoundedInput(io.BytesIO):
        def read(self, size=-1):
            assert 0 <= size <= 1_048_577, "unbounded draft allocation"
            return super().read(size)

    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs:
                        BoundedInput(json.dumps(INDEX_OUTCOME).encode()))
    assert main(["preview", "--outcome", "synthetic.json"]) == 0
    assert json.loads(capsys.readouterr().out)["post"]["room"] == "findings"
