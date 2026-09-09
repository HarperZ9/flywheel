import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
REPO = Path(__file__).resolve().parents[1]


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


def _flywheel(root: Path, py: Path, home: Path, args: list[str]) -> dict:
    exe = root / ("Scripts/flywheel.exe" if os.name == "nt" else "bin/flywheel")
    cmd = [str(exe), "writing", *args] if exe.exists() else [
        str(py), "-m", "harness.cli_entry", "writing", *args]
    env = {**os.environ, "FLYWHEEL_HOME": str(home)}
    env.pop("PYTHONPATH", None); env.pop("FLYWHEEL_REPO", None)
    run = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
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
