"""Falsifiers for the articulate lane (harness/articulate_mcp.py).

The load-bearing check is parity: the lane's ``check`` tool must return exactly
what ``python -m articulate.cli check`` returns for the same text, so the
zero-dependency MCP shim can never silently reshape the detector's result. The
rest guards the transport (JSON-RPC over stdio), the health tools a lane probe
reads, and the graceful-unavailable path when the package is not importable.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

from harness import articulate_mcp

# The lane reads its detector from the installed articulate-writing package. With
# no package there is nothing to be in parity with, so the parity suite is skipped
# rather than failed; the unavailable-path test below covers the missing case.
pytest.importorskip("articulate")


# Texts chosen to exercise the three verdicts and the profile resolution path:
# a clean passage over the 30-word floor, a banned device (em-dash), the
# AI-register vocabulary, and an in-text profile tag that must resolve the same
# way in the lane as in the CLI.
SAMPLES = {
    "clean_over_floor": (
        "The crew stacked the logs by the road before noon. We counted forty "
        "rounds and split the biggest ones by hand. The truck came late, so the "
        "last load waited until the light was nearly gone."),
    "em_dash_device": (
        "The plan was simple enough on paper — the ground told a different "
        "story once the rain set in and the slope turned to mud underfoot."),
    "register_words": (
        "This robust and seamless solution will leverage a holistic framework to "
        "delve into the landscape and unlock a transformative, game-changing "
        "paradigm for every stakeholder in the ecosystem."),
    "declared_profile": (
        "writing-profile: procedure\n\n"
        "Open the valve. Wait for the gauge to settle. Close the valve and log "
        "the reading before you move on to the next station on the line."),
}


def _cli_check(text: str) -> dict:
    """Run the reference CLI on the same text via stdin and return results[0].

    Bytes in, bytes out, with PYTHONUTF8 forced, so a device character (the
    em-dash) round-trips unmangled on every platform and no newline translation
    perturbs the comparison.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "articulate.cli", "check", "--json"],
        input=text.encode("utf-8"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**_utf8_env()}, timeout=60, check=True)
    payload = json.loads(proc.stdout.decode("utf-8"))
    return payload["results"][0]


def _utf8_env() -> dict:
    import os
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_lane_check_matches_cli_check(name):
    text = SAMPLES[name]
    cli = _cli_check(text)
    # The CLI adds `file` (the input name, "<stdin>"); the lane screens provided
    # text, so it has no file. Everything else must be identical.
    cli.pop("file", None)
    lane = articulate_mcp.do_check(text)
    assert lane == cli


def test_parity_covers_each_verdict():
    # The corpus is only a real parity check if it actually spans the verdicts.
    verdicts = {articulate_mcp.do_check(t)["verdict"] for t in SAMPLES.values()}
    assert {"clean", "flagged"} <= verdicts


def test_check_tool_over_jsonrpc_equals_do_check():
    text = SAMPLES["register_words"]
    req = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
           "params": {"name": "check", "arguments": {"text": text}}}
    resp = articulate_mcp.handle_request(req)
    body = json.loads(resp["result"]["content"][0]["text"])
    assert body == articulate_mcp.do_check(text)
    assert body["verdict"] == "flagged" and body["gate"] == "blocked"


def test_score_is_consistent_with_check():
    text = SAMPLES["register_words"]
    score = articulate_mcp.do_score(text)
    check = articulate_mcp.do_check(text)
    assert score["texture_score"] == check["texture_score"]
    assert score["hard_hits"] == len(check["high"]) + len(check["medium"])
    assert score["verdict"] == check["verdict"]
    assert score["words"] == check["cadence"]["words"]


def test_profile_override_changes_the_gate():
    # A stock connective ("moreover") is a MEDIUM tell: it gates under a strict-slop
    # profile (procedure) and not under the flavored default. The override, which is
    # a profile name and not a slop level, must reach the detector.
    text = ("Moreover, the results were consistent across every run we made, and "
            "the totals matched the ledger to the last entry without exception.")
    assert articulate_mcp.do_check(text)["gate"] == "ok"
    assert articulate_mcp.do_check(text, profile="procedure")["gate"] == "blocked"


def test_initialize_and_tools_list():
    init = articulate_mcp.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "articulate"
    assert init["result"]["protocolVersion"] == articulate_mcp.PROTOCOL
    listed = articulate_mcp.handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in listed["result"]["tools"]}
    assert names == {"check", "score", "articulate.status", "articulate.doctor"}


def test_status_and_doctor_report_healthy_with_detector_present():
    for tool, deep in (("articulate.status", False), ("articulate.doctor", True)):
        resp = articulate_mcp.handle_request(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": tool, "arguments": {}}})
        health = json.loads(resp["result"]["content"][0]["text"])
        assert health["ok"] is True
        assert health["server"] == "articulate"
        assert health["detector_version"] == articulate_mcp.ARTICULATE_VERSION
        if deep:
            assert set(health["tools"]) == {
                "check", "score", "articulate.status", "articulate.doctor"}


def test_serve_loop_answers_a_line():
    import io
    stdin = io.StringIO(json.dumps(
        {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
         "params": {"name": "check", "arguments": {"text": SAMPLES["clean_over_floor"]}}}
    ) + "\n")
    stdout = io.StringIO()
    assert articulate_mcp.serve(stdin, stdout) == 0
    resp = json.loads(stdout.getvalue().strip())
    body = json.loads(resp["result"]["content"][0]["text"])
    assert body == articulate_mcp.do_check(SAMPLES["clean_over_floor"])


def test_unavailable_detector_degrades_without_crashing(monkeypatch):
    # Simulate a missing articulate-writing package: check/score return a clean
    # unavailable error and the health tools report not-healthy, so a lane probe
    # records the lane as stale rather than the server failing to launch.
    monkeypatch.setattr(articulate_mcp, "_check_text", None)
    monkeypatch.setattr(articulate_mcp, "_profiles", None)
    monkeypatch.setattr(articulate_mcp, "ARTICULATE_VERSION", None)
    monkeypatch.setattr(articulate_mcp, "_IMPORT_ERROR", "ModuleNotFoundError: articulate")

    resp = articulate_mcp.handle_request(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "check", "arguments": {"text": "anything at all"}}})
    body = json.loads(resp["result"]["content"][0]["text"])
    assert body["error"]["code"] == "ARTICULATE_UNAVAILABLE"

    status = articulate_mcp.handle_request(
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "articulate.status", "arguments": {}}})
    health = json.loads(status["result"]["content"][0]["text"])
    assert health["ok"] is False


def test_missing_text_argument_is_reported():
    resp = articulate_mcp.handle_request(
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
         "params": {"name": "check", "arguments": {}}})
    body = json.loads(resp["result"]["content"][0]["text"])
    assert body["error"]["code"] == "INVALID_ARGUMENTS"


def test_do_check_does_not_mutate_across_calls():
    # check_text builds a fresh dict per call; guard against a shared-state
    # regression that would make parity order-dependent.
    text = SAMPLES["em_dash_device"]
    first = copy.deepcopy(articulate_mcp.do_check(text))
    second = articulate_mcp.do_check(text)
    assert first == second
