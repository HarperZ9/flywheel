import json
import os
from pathlib import Path
import subprocess
import sys

from harness.writing_types import sha256_bytes

PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CARD = "card_" + "9" * 32
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
                   check=True,
                   cwd=root, capture_output=True, text=True)
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


def test_installed_cli_and_stdio_mcp_author_pipeline(tmp_path):
    py = _venv_python(tmp_path / "venv")
    home = tmp_path / "home"
    brief = tmp_path / "brief.json"; sources = tmp_path / "sources.json"
    brief.write_text(json.dumps({"schema": "flywheel.writing-project-brief/v1",
        "project_ref": PROJECT, "mode": "nonfiction", "form": "essay",
        "working_title": "Release evidence", "audience": "operators",
        "reader_job": "decide whether to publish",
        "author_intent": "publish after receipts match",
        "voice_contract": {"style_ref": "voice_rules"},
        "source_packet_ref": "packet_main", "writing_profile": "nonfiction",
        "does_not_prove": ["truth"]}), encoding="utf-8")
    sources.write_text(json.dumps({"schema": "flywheel.writing-source-packet/v1",
        "project_ref": PROJECT, "source_packet_ref": "packet_main",
        "sources": [{"source_id": "src_receipt", "title": "Receipt",
        "origin": "local", "allowed_use": "cite"}],
        "does_not_prove": ["interpretation"]}), encoding="utf-8")
    proposal = _flywheel(tmp_path / "venv", py, home, [
        "init", "--brief", str(brief), "--source-packet", str(sources),
        "--client-request-id", "init", "--prepare", "--json"])
    ack = _approve_commit(tmp_path / "venv", py, home, proposal)
    journey, head = ack["journey_ref"], ack["event_head_sha256"]

    section = tmp_path / "section.json"
    section.write_text(json.dumps({"schema": "flywheel.writing-section/v1",
        "project_ref": PROJECT, "section_ref": "sec_recommendation",
        "heading": "Recommendation", "purpose": "state the release decision",
        "reader_entry_state": "needs a decision",
        "promises": ["states the decision"], "order_index": 1}), encoding="utf-8")
    stale = _flywheel(tmp_path / "venv", py, home, ["section", "add",
        "--journey-ref", journey, "--expected-event-head", "0" * 64,
        "--client-request-id", "stale", "--prepare", "--json",
        "--section-json", str(section)])
    assert stale["error"]["code"] == "HEAD_CONFLICT"
    head = _approve_commit(tmp_path / "venv", py, home, _flywheel(
        tmp_path / "venv", py, home, ["section", "add", "--journey-ref", journey,
        "--expected-event-head", head, "--client-request-id", "section",
        "--prepare", "--json", "--section-json", str(section)]))["event_head_sha256"]
    original = tmp_path / "original.txt"; original.write_text(
        "Recommendation: hold.\n", encoding="utf-8")
    revision = _flywheel(tmp_path / "venv", py, home, ["revision", "record",
        "--journey-ref", journey, "--expected-event-head", head, "--project", PROJECT,
        "--section", "sec_recommendation", "--body", str(original),
        "--client-request-id", "revision", "--prepare", "--json"])
    head = _approve_commit(tmp_path / "venv", py, home, revision)["event_head_sha256"]
    diag = _flywheel(tmp_path / "venv", py, home, ["diagnose",
        "--journey-ref", journey, "--expected-event-head", head,
        "--project", PROJECT, "--revision", revision["revision_ref"],
        "--client-request-id", "diagnose", "--prepare", "--json"])
    diag_view = _flywheel(tmp_path / "venv", py, home, [
        "proposal", "get", diag["proposal_ref"], "--json"])
    diagnostic_ref = diag_view["writing_artifact"]["artifact_id"]
    head = _approve_commit(tmp_path / "venv", py, home, diag)["event_head_sha256"]
    card = tmp_path / "card.json"
    start = len("Recommendation: "); end = start + len("hold")
    card.write_text(json.dumps({"schema": "flywheel.writing-scoped-revision/v1",
        "project_ref": PROJECT, "card_ref": CARD,
        "diagnostic_ref": diagnostic_ref, "problem": "Reflect release evidence.",
        "goal": "replace only the recommendation",
        "must_preserve": ["outside selected span"], "allowed_operations": ["replace"],
        "forbidden_operations": ["change context"], "source_refs": ["src_receipt"],
        "voice_constraints": "direct",
        "target": {"section_ref": "sec_recommendation",
        "base_revision_ref": revision["revision_ref"],
        "base_body_sha256": revision["body_sha256"], "coordinate_type": "unicode_codepoint", "start": start, "end": end,
        "selected_span_sha256": sha256_bytes(b"hold")},
        "does_not_prove": ["quality"]}), encoding="utf-8")
    head = _approve_commit(tmp_path / "venv", py, home, _flywheel(
        tmp_path / "venv", py, home, ["card", "record", "--journey-ref", journey,
        "--expected-event-head", head, "--client-request-id", "card",
        "--prepare", "--json", "--card-json", str(card)]))["event_head_sha256"]

    mcp_env = {**os.environ, "FLYWHEEL_HOME": str(home)}
    proc = subprocess.Popen([str(py), "-m", "harness.writing_mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=tmp_path,
        env=mcp_env)
    try:
        proc.stdin.write("[]\n"); proc.stdin.flush()
        tools = _rpc(proc, {"jsonrpc": "2.0", "id": 0,
            "method": "tools/list"})["result"]["tools"]
        schemas = {tool["name"]: tool["inputSchema"] for tool in tools}
        assert "section" in schemas["writing.section_record"]["properties"]
        assert "body" in schemas["writing.candidate_record"]["properties"]
        assert "proposal_ref" in schemas["writing.proposal_get"]["properties"]
        assert "revision_ref" in schemas["writing.diagnose"]["properties"]
        bad = _mcp_call(proc, "writing.status", {"extra": "x"}, 1)
        assert bad["error"]["code"] == "INVALID_ARGUMENTS"
        old_card = _mcp_call(proc, "writing.card_record", {
            "journey_ref": journey, "expected_event_head": head,
            "client_request_id": "old-card", "card": {
            "schema": "flywheel.writing-card/v1", "project_ref": PROJECT,
            "card_ref": "card_old", "kind": "revise",
            "problem_summary": "old", "reported_by": "fixture",
            "target": {"section_ref": "sec_recommendation",
            "base_revision_ref": revision["revision_ref"],
            "base_body_sha256": revision["body_sha256"], "coordinate_type": "unicode_codepoint", "start": 0, "end": 22,
            "selected_span_sha256": revision["body_sha256"]},
            "does_not_prove": ["quality"]}}, 6)
        assert old_card["error"]["code"] == "ARTIFACT_SCHEMA_INVALID"
        env_status = _mcp_call(proc, "writing.status", {}, 2)
        assert env_status["projects"][0]["journey_ref"] == journey
        oos = _mcp_call(proc, "writing.candidate_record", {
            "journey_ref": journey, "expected_event_head": head,
            "project_ref": PROJECT, "card_ref": CARD,
            "body": "OUTSIDE SCOPE\n", "client_request_id": "oos"}, 7)
        assert oos["scope_verdict"] == "HOLD"
        head = _approve_commit(tmp_path / "venv", py, home, oos)["event_head_sha256"]
        supersede = _flywheel(tmp_path / "venv", py, home, [
            "decision", "record", "--journey-ref", journey,
            "--expected-event-head", head, "--client-request-id", "supersede",
            "--prepare", "--json", "--project", PROJECT,
            "--decision", "supersede", "--candidate", oos["candidate_ref"]])
        head = _approve_commit(tmp_path / "venv", py, home, supersede)["event_head_sha256"]
        after_supersede = _mcp_call(proc, "writing.export_prepare", {
            "journey_ref": journey, "expected_event_head": head,
            "project_ref": PROJECT, "out_ref": "after_supersede",
            "client_request_id": "after-supersede"}, 8)
        head = _approve_commit(tmp_path / "venv", py, home, after_supersede)["event_head_sha256"]
        manifest = json.loads((home / "state" / "artifacts" /
            after_supersede["artifact_ref"]).read_text())
        manuscript = (home / "state" / "artifacts" /
            manifest["manuscript_ref"]).read_text()
        assert manuscript == "Recommendation: hold.\n"
        candidate = _mcp_call(proc, "writing.candidate_record", {
            "journey_ref": journey, "expected_event_head": head,
            "project_ref": PROJECT, "card_ref": CARD,
            "body": "Recommendation: release.\n",
            "client_request_id": "candidate"}, 3)
        assert candidate["scope_verdict"] == "PASS"
        preview = _mcp_call(proc, "writing.proposal_get", {
            "proposal_ref": candidate["proposal_ref"]}, 4)
        assert preview["writing_artifact"]["kind"] == "candidate"
        assert preview["approval_preview"]["candidate_body"] == "Recommendation: release.\n"
        assert preview["approval_preview"]["base_revision_ref"] == revision["revision_ref"]
        assert preview["approval_preview"]["stored_scope_receipt_matches"] is True
        head = _approve_commit(tmp_path / "venv", py, home, candidate)["event_head_sha256"]
        accept = _flywheel(tmp_path / "venv", py, home, ["decision", "record",
            "--journey-ref", journey, "--expected-event-head", head,
            "--client-request-id", "accept", "--prepare", "--json",
            "--project", PROJECT, "--decision", "accept",
            "--candidate", candidate["candidate_ref"]])
        approval_view = _flywheel(tmp_path / "venv", py, home, [
            "proposal", "get", accept["proposal_ref"], "--json"])
        assert approval_view["writing_artifact"]["kind"] == "decision"
        assert approval_view["approval_preview"]["scope_verdict"] == "PASS"
        grant = _flywheel(tmp_path / "venv", py, home, [
            "proposal", "approve", accept["proposal_ref"], "--json"])
        committed = _flywheel(tmp_path / "venv", py, home, [
            "proposal", "commit", accept["proposal_ref"],
            "--grant", grant["grant_ref"], "--json"])
        replay = _flywheel(tmp_path / "venv", py, home, [
            "proposal", "commit", accept["proposal_ref"],
            "--grant", grant["grant_ref"], "--json"])
        assert replay["event_head_sha256"] == committed["event_head_sha256"]
        head = committed["event_head_sha256"]
        export = _mcp_call(proc, "writing.export_prepare", {
            "journey_ref": journey, "expected_event_head": head,
            "project_ref": PROJECT, "out_ref": "article",
            "client_request_id": "export"}, 5)
    finally:
        proc.terminate(); proc.wait(timeout=10)
    final = _approve_commit(tmp_path / "venv", py, home, export)
    status = _flywheel(tmp_path / "venv", py, home, ["status", "--json"])
    manifest = json.loads((home / "state" / "artifacts" / export["artifact_ref"]).read_text())
    manuscript = (home / "state" / "artifacts" / manifest["manuscript_ref"]).read_text()
    assert final["journey_ref"] == journey
    assert status["projects"][0]["event_head_sha256"] == final["event_head_sha256"]
    assert manuscript == "Recommendation: release.\n"
