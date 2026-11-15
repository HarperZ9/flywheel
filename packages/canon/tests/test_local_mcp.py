"""test_local_mcp.py -- the MCP door.

Two things are under test. The protocol shape a harness depends on: the tool
names, the initialize reply, and the error path for a call that cannot be
served. And the claim the server makes about itself, that every tool here
reads, which is asserted against bytes on disk rather than taken on the
server's word.

The status/doctor split matters to a probe. `canon.status` answers whether the
server is alive and stays true whatever the block directory holds; `canon.doctor`
answers whether it is ready and reads false when the directory is missing or
holds a file that will not load. A doctor that cannot be false is not a check.
"""
from __future__ import annotations

import hashlib
import io
import json

from canon.blocks import ENV_BLOCKS_DIR
from canon import local_mcp
from canon.local_mcp import ENV_HOME, ENV_WORKSPACE, PROTOCOL, TOOLS, handle, serve
from canon.schema import KIND_PERSONALITY_BLOCK, Record

from ._mcp_helpers import (  # noqa: F401  (_clean_env is an autouse fixture)
    TOOL_NAMES,
    _block,
    _call,
    _clean_env,
    _memory,
    _payload,
    _seed,
    _tool,
)


def test_initialize_answers_with_the_pinned_protocol_and_name():
    result = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})["result"]
    assert result["protocolVersion"] == PROTOCOL
    assert result["serverInfo"]["name"] == "canon"
    assert "tools" in result["capabilities"]


def test_the_tool_list_carries_the_names_a_lane_probe_looks_for():
    # harness/lanes.py probes a lane by calling `<name>.status` or
    # `<name>.doctor`. A rename here silently downgrades the lane to unprobed.
    listed = [t["name"] for t in handle({"id": 2, "method": "tools/list"})["result"]["tools"]]
    assert listed == TOOL_NAMES
    assert "canon.status" in listed and "canon.doctor" in listed


def test_every_tool_declares_an_object_input_schema():
    for tool in TOOLS:
        assert tool["inputSchema"]["type"] == "object"
        assert tool["description"].strip()


def test_an_unknown_method_is_an_error_not_a_silent_empty_result():
    resp = handle({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
    assert resp["error"]["code"] == -32601


def test_a_notification_gets_no_reply():
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_an_unknown_tool_is_reported_as_an_error():
    result = _call("canon.nope")
    assert result["isError"] is True
    assert "canon.nope" in result["content"][0]["text"]


def test_status_stays_true_when_the_block_directory_is_gone(tmp_path, monkeypatch):
    # Liveness is not readiness. A probe asking whether the server answers must
    # not get a false from a directory that was never configured.
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(tmp_path / "does-not-exist"))
    status = _tool("canon.status")
    assert status["ok"] is True and status["server"] == "canon"
    assert status["protocol"] == PROTOCOL


def test_doctor_reads_false_for_a_missing_directory(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(tmp_path / "does-not-exist"))
    doctor = _tool("canon.doctor")
    assert doctor["ok"] is False
    assert doctor["blocks_loaded"] == 0 and doctor["block_problems"]
    assert doctor["drift_roots_configured"] is False


def test_doctor_reads_true_once_the_directory_loads(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"))))
    doctor = _tool("canon.doctor")
    assert doctor["ok"] is True and doctor["blocks_loaded"] == 1
    assert doctor["block_problems"] == []
    assert doctor["tools"] == TOOL_NAMES
    # Every write surface is named, so a caller can see what canon claims
    # authority over without reading this repository.
    from canon.registry import SURFACE_CATALOG
    assert len(doctor["surfaces"]) == len(SURFACE_CATALOG) == 7


def test_doctor_sees_the_drift_roots_once_they_are_set(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"))))
    monkeypatch.setenv(ENV_HOME, str(tmp_path))
    monkeypatch.setenv(ENV_WORKSPACE, str(tmp_path))
    assert _tool("canon.doctor")["drift_roots_configured"] is True


def test_blocks_lists_identity_and_title(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"), _memory("m1"))))
    listing = _tool("canon.blocks")
    assert listing["count"] == 2 and listing["problems"] == []
    assert {b["id"] for b in listing["blocks"]} == {"b1", "m1"}
    by_id = {b["id"]: b for b in listing["blocks"]}
    assert by_id["b1"]["title"] == "B1" and by_id["b1"]["kind"] == KIND_PERSONALITY_BLOCK
    # An episodic memory has no title. Reporting None beats inventing one.
    assert by_id["m1"]["title"] is None


def test_blocks_full_returns_records_that_reconstruct(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"))))
    full = _tool("canon.blocks", {"full": True})
    assert Record.from_dict(full["blocks"][0]) == _block("b1")


def test_render_returns_the_text_the_surface_writer_would_splice(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"), _block("b2", ord_=2))))
    rendered = _tool("canon.render", {"scope": "global"})
    assert rendered["blocks_rendered"] == 2 and rendered["records_excluded"] == 0
    assert "B1" in rendered["text"] and "B2" in rendered["text"]
    assert 'canon:block id="b1"' in rendered["text"]


def test_render_counts_what_it_left_out_rather_than_refusing(tmp_path, monkeypatch):
    # Layering accepts personality blocks only. A memory sitting in the same
    # directory would turn every render into a refusal, so it is filtered and
    # the count of what was dropped is reported beside the text.
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"), _memory("m1"))))
    rendered = _tool("canon.render", {"scope": "global"})
    assert rendered["blocks_rendered"] == 1 and rendered["records_excluded"] == 1
    assert "m1" not in rendered["text"]


def test_render_refuses_a_scope_that_is_not_a_scope(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"))))
    result = _call("canon.render", {"scope": "repo"})
    assert result["isError"] is True
    assert "repo" in result["content"][0]["text"]


def test_validate_reports_a_bad_record_by_field(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(tmp_path))
    payload = _block("b1").to_dict()
    payload["provenance"]["source_hash"] = "not-a-digest"
    report = _tool("canon.validate", {"record": payload})
    assert report["ok"] is False and report["id"] == "b1"
    assert any("source_hash" in p for p in report["problems"])


def test_validate_with_no_record_checks_the_whole_directory(tmp_path, monkeypatch):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"))))
    report = _tool("canon.validate")
    assert report["target"] == "blocks" and report["ok"] is False
    # One loaded, one refused: the file count is conserved in `checked`.
    assert report["checked"] == 2


def test_serve_round_trips_a_request_over_a_stream(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"))))
    lines = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
             "",
             json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
             json.dumps({"not": "json-rpc but parseable"}),
             "{ this line does not parse",
             json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                         "params": {"name": "canon.status"}})]
    out = io.StringIO()
    assert serve(io.StringIO("\n".join(lines) + "\n"), out) == 0
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    # Blank lines, unparseable lines, and the notification produce no reply; a
    # malformed object with no id is a notification as far as the loop is
    # concerned. Two requests in, two replies out.
    assert [r["id"] for r in replies] == [1, 2]
    assert json.loads(replies[1]["result"]["content"][0]["text"])["server"] == "canon"


def _digest_tree(root) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_no_tool_on_this_server_writes_anything(tmp_path, monkeypatch):
    """The false-success control behind the server's own `writes: none` claim.

    Every tool runs against a populated block directory with the drift roots
    pointed at a tree holding a real managed surface, which is the arrangement
    where a write would actually land somewhere. The tree is digested before and
    after. A tool that grew a write would change a hash here.
    """
    blocks = _seed(tmp_path / "blocks", _block("b1"), _memory("m1")) \
        if (tmp_path / "blocks").mkdir() or True else None
    home, workspace = tmp_path / "home", tmp_path / "ws"
    for root in (home, workspace):
        root.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude" / "CLAUDE.md").write_text(
        "# host prose\n<!-- canon:begin scope=global -->\n<!-- canon:end -->\n",
        encoding="utf-8")
    (workspace / "CLAUDE.md").write_text("# workspace, no canon region\n", encoding="utf-8")
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(blocks))
    monkeypatch.setenv(ENV_HOME, str(home))
    monkeypatch.setenv(ENV_WORKSPACE, str(workspace))

    before = _digest_tree(tmp_path)
    for name in TOOL_NAMES:
        args = {"scope": "global"} if name == "canon.render" else {}
        _call(name, args)
    _call("canon.blocks", {"full": True})
    _call("canon.validate", {"record": _block("b1").to_dict()})
    assert _digest_tree(tmp_path) == before


def test_the_served_version_is_the_packaged_version():
    """One number. A harness reads serverInfo, a lane reads install metadata.

    If those disagree, a lane roster reports a version the server never claimed
    and the mismatch looks like a stale install rather than a typo here. The
    package's own `canon.__version__` is the number `canon --version` prints,
    so it is held to the same line.
    """
    from pathlib import Path

    import canon

    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml"
                 ).read_text(encoding="utf-8")
    declared = next(line.split("=", 1)[1].strip().strip('"')
                    for line in pyproject.splitlines()
                    if line.startswith("version"))
    assert local_mcp.__version__ == declared
    assert canon.__version__ == declared
