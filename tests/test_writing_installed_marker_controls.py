import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
REPO = Path(__file__).resolve().parents[1]
_FLYWHEEL_TIMEOUT_S = 45.0
_DIAGNOSTIC_TEXT_LIMIT = 500
_SECRET_ASSIGNMENT = re.compile(
    r"\b([A-Za-z0-9_]*(?:TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY|PRIVATE_KEY))"
    r"\s*[:=]\s*([^\s,;]+)",
    re.IGNORECASE,
)


def _redact_diagnostic_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", "replace")
    else:
        text = str(value)
    text = text.replace("\x00", "\\x00")
    text = _SECRET_ASSIGNMENT.sub(r"\1=<redacted>", text)
    if len(text) > _DIAGNOSTIC_TEXT_LIMIT:
        return text[:_DIAGNOSTIC_TEXT_LIMIT] + "...<truncated>"
    return text


def _flywheel_phase(args: list[str]) -> str:
    if not args:
        return "writing"
    if len(args) > 1 and not args[1].startswith("-"):
        return f"{args[0]} {args[1]}"
    return args[0]


def _sanitized_args(args: list[str]) -> list[str]:
    safe = []
    for arg in args:
        text = _redact_diagnostic_text(arg)
        if "/" in text or "\\" in text or re.match(r"^[A-Za-z]:", text):
            name = text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
            safe.append(f"<path:{name or 'path'}>")
        else:
            safe.append(text)
    return safe


def _venv_python(root: Path) -> Path:
    exe = root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    wheelhouse = root.parent / "wheelhouse"
    wheelhouse.mkdir()
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps",
                    "--no-build-isolation", "-w", str(wheelhouse), str(REPO)],
                   check=True, cwd=REPO, capture_output=True, text=True)
    subprocess.run([sys.executable, "-m", "venv", str(root)], check=True)
    subprocess.run([str(exe), "-m", "pip", "install", "--no-index",
                    "--find-links", str(wheelhouse), "flywheel-verify"],
                   check=True, cwd=root, capture_output=True, text=True)
    return exe


def _flywheel(root: Path, py: Path, home: Path, args: list[str],
              timeout_s: float = _FLYWHEEL_TIMEOUT_S) -> dict:
    exe = root / ("Scripts/flywheel.exe" if os.name == "nt" else "bin/flywheel")
    cmd = [str(exe), "writing", *args] if exe.exists() else [
        str(py), "-m", "harness.cli_entry", "writing", *args]
    env = {**os.environ, "FLYWHEEL_HOME": str(home)}
    env.pop("PYTHONPATH", None); env.pop("FLYWHEEL_REPO", None)
    try:
        run = subprocess.run(cmd, cwd=root, env=env, capture_output=True,
                             text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        phase = _flywheel_phase(args)
        raise AssertionError(
            "flywheel writing command timed out after "
            f"{timeout_s:.1f}s during {phase}; "
            f"args={json.dumps(_sanitized_args(args))}; "
            f"stdout={_redact_diagnostic_text(exc.stdout)!r}; "
            f"stderr={_redact_diagnostic_text(exc.stderr)!r}"
        ) from None
    assert run.stdout.strip(), run.stderr
    result = json.loads(run.stdout)
    if run.returncode:
        result["_returncode"] = run.returncode
    return result


def _approve_commit(root, py, home, proposal):
    grant = _flywheel(root, py, home, [
        "proposal", "approve", proposal["proposal_ref"], "--json"])
    return _flywheel(root, py, home, [
        "proposal", "commit", proposal["proposal_ref"],
        "--grant", grant["grant_ref"], "--json"])


def _rpc(proc, request):
    proc.stdin.write(json.dumps(request) + "\n"); proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def _mcp_call(proc, name, arguments, ident):
    request = {"jsonrpc": "2.0", "id": ident, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    response = _rpc(proc, request)
    return json.loads(response["result"]["content"][0]["text"])


def test_flywheel_helper_timeout_reports_phase_and_sanitizes_child_output(tmp_path):
    root = tmp_path / "fake-venv"
    package = root / "harness"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli_entry.py").write_text(
        "import sys, time\n"
        "print('stdout before hang SECRET_TOKEN=stdout-secret', flush=True)\n"
        "print('stderr before hang PASSWORD=stderr-secret', file=sys.stderr, flush=True)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError) as raised:
        _flywheel(root, Path(sys.executable), tmp_path / "home",
                  ["proposal", "approve", "prp_test", "--json"],
                  timeout_s=3.0)

    message = str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__
    assert "proposal approve" in message
    assert "timed out after" in message
    assert "stdout before hang" in message
    assert "stderr before hang" in message
    assert "stdout-secret" not in message
    assert "stderr-secret" not in message
    assert "SECRET_TOKEN=<redacted>" in message
    assert "PASSWORD=<redacted>" in message
    assert "PYTHONPATH" not in message
    assert "FLYWHEEL_HOME" not in message


def test_installed_mcp_diagnoses_known_and_unknown_source_markers(tmp_path):
    py = _venv_python(tmp_path / "venv")
    home = tmp_path / "home"
    brief = tmp_path / "brief.json"; sources = tmp_path / "sources.json"
    brief.write_text(json.dumps({"schema": "flywheel.writing-project-brief/v1",
        "project_ref": PROJECT, "mode": "nonfiction", "form": "essay",
        "working_title": "Release evidence", "audience": "operators",
        "reader_job": "decide whether to publish", "author_intent": "publish after receipts match",
        "voice_contract": {"style_ref": "voice_rules"}, "source_packet_ref": "packet_main",
        "writing_profile": "nonfiction", "does_not_prove": ["truth"]}), encoding="utf-8")
    sources.write_text(json.dumps({"schema": "flywheel.writing-source-packet/v1",
        "project_ref": PROJECT, "source_packet_ref": "packet_main",
        "sources": [{"source_id": "src_receipt", "title": "Receipt", "origin": "local",
        "allowed_use": "cite"}, {"source_id": "src_unused", "title": "Unused",
        "origin": "local", "allowed_use": "cite"}],
        "does_not_prove": ["interpretation"]}), encoding="utf-8")
    proposal = _flywheel(tmp_path / "venv", py, home, ["init", "--brief", str(brief),
        "--source-packet", str(sources), "--client-request-id", "init", "--prepare", "--json"])
    ack = _approve_commit(tmp_path / "venv", py, home, proposal)
    journey, head = ack["journey_ref"], ack["event_head_sha256"]
    section = tmp_path / "section.json"
    section.write_text(json.dumps({"schema": "flywheel.writing-section/v1",
        "project_ref": PROJECT, "section_ref": "sec_recommendation",
        "heading": "Recommendation", "purpose": "state the release decision",
        "reader_entry_state": "needs a decision", "promises": ["states the decision"],
        "order_index": 1}), encoding="utf-8")
    head = _approve_commit(tmp_path / "venv", py, home, _flywheel(
        tmp_path / "venv", py, home, ["section", "add", "--journey-ref", journey,
        "--expected-event-head", head, "--client-request-id", "section",
        "--prepare", "--json", "--section-json", str(section)]))["event_head_sha256"]
    known = tmp_path / "known.txt"
    known.write_text("Recommendation: release. [src_receipt]\n", encoding="utf-8")
    known_rev = _flywheel(tmp_path / "venv", py, home, ["revision", "record",
        "--journey-ref", journey, "--expected-event-head", head, "--project", PROJECT,
        "--section", "sec_recommendation", "--body", str(known),
        "--client-request-id", "known", "--prepare", "--json"])
    head = _approve_commit(tmp_path / "venv", py, home, known_rev)["event_head_sha256"]
    proc = subprocess.Popen([str(py), "-m", "harness.writing_mcp"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, text=True, cwd=tmp_path, env={**os.environ, "FLYWHEEL_HOME": str(home)})
    try:
        known_diag = _mcp_call(proc, "writing.diagnose", {"journey_ref": journey,
            "expected_event_head": head, "project_ref": PROJECT,
            "revision_ref": known_rev["revision_ref"], "client_request_id": "known-diag"}, 1)
        known_artifact = json.loads((home / "state" / "artifacts" / known_diag["artifact_ref"]).read_text())
        assert known_artifact["source_grounding"][0]["status"] == "known_source"
        assert known_artifact["source_grounding"][0]["span_refs"][0]["excerpt"] == "[src_receipt]"
        head = _approve_commit(tmp_path / "venv", py, home, known_diag)["event_head_sha256"]
        review = _mcp_call(proc, "writing.review_prepare", {"journey_ref": journey,
            "expected_event_head": head, "project_ref": PROJECT,
            "client_request_id": "known-review"}, 2)
        review_artifact = json.loads((home / "state" / "artifacts" / review["artifact_ref"]).read_text())
        assert review_artifact["source_coverage"]["source_refs"] == ["src_receipt"]
        head = _approve_commit(tmp_path / "venv", py, home, review)["event_head_sha256"]
        unknown = tmp_path / "unknown.txt"
        unknown.write_text("Recommendation: release. [src_missing]\n", encoding="utf-8")
        unknown_rev = _flywheel(tmp_path / "venv", py, home, ["revision", "record",
            "--journey-ref", journey, "--expected-event-head", head, "--project", PROJECT,
            "--section", "sec_recommendation", "--body", str(unknown),
            "--client-request-id", "unknown", "--prepare", "--json"])
        head = _approve_commit(tmp_path / "venv", py, home, unknown_rev)["event_head_sha256"]
        unknown_diag = _mcp_call(proc, "writing.diagnose", {"journey_ref": journey,
            "expected_event_head": head, "project_ref": PROJECT,
            "revision_ref": unknown_rev["revision_ref"], "client_request_id": "unknown-diag"}, 4)
        unknown_artifact = json.loads((home / "state" / "artifacts" / unknown_diag["artifact_ref"]).read_text())
        assert unknown_artifact["source_grounding"][0]["status"] == "unknown_source"
        assert unknown_artifact["problems"][0]["source_id"] == "src_missing"
    finally:
        proc.terminate(); proc.wait(timeout=10)
