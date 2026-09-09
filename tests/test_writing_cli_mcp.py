import json
import os
import subprocess
import sys

from harness import writing_mcp


REPO = os.path.dirname(os.path.dirname(__file__))
PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _write_inputs(tmp_path):
    brief = tmp_path / "brief.json"
    sources = tmp_path / "sources.json"
    brief.write_text(json.dumps({
        "schema": "flywheel.writing-project-brief/v1",
        "project_ref": PROJECT,
        "mode": "nonfiction",
        "form": "essay",
        "working_title": "Release evidence",
        "audience": "operators",
        "reader_job": "decide whether to publish",
        "author_intent": "bounded release note",
        "voice_contract": {"style_ref": "voice_rules"},
        "source_packet_ref": "packet_main",
        "writing_profile": "nonfiction",
        "does_not_prove": ["truth"],
    }), encoding="utf-8")
    sources.write_text(json.dumps({
        "schema": "flywheel.writing-source-packet/v1",
        "project_ref": PROJECT,
        "source_packet_ref": "packet_main",
        "sources": [{"source_id": "src_receipt", "title": "Receipt",
                     "origin": "local", "allowed_use": "cite"}],
        "does_not_prove": ["interpretation"],
    }), encoding="utf-8")
    return brief, sources


def _run(args, home):
    env = os.environ.copy()
    env["FLYWHEEL_HOME"] = str(home)
    env["PYTHONPATH"] = REPO
    return subprocess.run(
        [sys.executable, "-m", "harness.cli_entry", "writing", *args],
        cwd=REPO, env=env, capture_output=True, text=True, check=False)


def test_cli_prepare_approve_commit_survives_separate_processes(tmp_path):
    brief, sources = _write_inputs(tmp_path)
    home = tmp_path / "home"
    prepare = _run([
        "init", "--brief", str(brief), "--source-packet", str(sources),
        "--client-request-id", "init-1", "--prepare", "--json"], home)
    proposal = json.loads(prepare.stdout)
    approve = _run([
        "proposal", "approve", proposal["proposal_ref"], "--json"], home)
    grant = json.loads(approve.stdout)
    commit = _run([
        "proposal", "commit", proposal["proposal_ref"],
        "--grant", grant["grant_ref"], "--json"], home)
    status = _run(["status", "--json"], home)

    assert prepare.returncode == approve.returncode == commit.returncode == 0
    assert proposal["approval_required"] is True
    assert json.loads(commit.stdout)["journey_ref"].startswith("jrn_")
    assert json.loads(status.stdout)["projects"][0]["project_ref"] == PROJECT


def test_mcp_tools_prepare_only_and_cannot_self_approve(tmp_path):
    brief, sources = _write_inputs(tmp_path)
    home = tmp_path / "home"
    init = writing_mcp.handle_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "writing.project_init",
            "arguments": {
                "home": str(home),
                "brief_path": str(brief),
                "source_packet_path": str(sources),
                "client_request_id": "init-1",
            },
        },
    })
    approve = writing_mcp.handle_request({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "writing.proposal_approve",
            "arguments": {"home": str(home), "proposal_ref": "prp_" + "a" * 32},
        },
    })

    init_text = json.loads(init["result"]["content"][0]["text"])
    approve_text = json.loads(approve["result"]["content"][0]["text"])
    assert init_text["approval_required"] is True
    assert approve_text["error"]["code"] == "APPROVAL_UNAVAILABLE"
    tools = writing_mcp.handle_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/list",
    })["result"]["tools"]
    schemas = {tool["name"]: tool["inputSchema"] for tool in tools}
    assert "section" in schemas["writing.section_record"]["properties"]
    assert "body" in schemas["writing.candidate_record"]["properties"]
    assert "proposal_ref" in schemas["writing.proposal_get"]["properties"]
