"""The independent witness: skipped hooks and rewritten stores, seen from outside.

Outcomes asserted: a tool call in the harness transcript with no pre record is
DRIFT once the grace window has passed; a call inside the window is not yet
counted; Claude Code and Codex transcript shapes both join; thinking and
reasoning items are never read as calls; with no readable transcript the
verdict is UNVERIFIABLE, never MATCH; a store rewritten after a head export is
DRIFT even when the rewritten chain is internally consistent; and the hook
exports heads to the owner's witness directory at every stop.
"""
from __future__ import annotations

import io
import json

from harness.preaction import cli
from harness.preaction.hook_setup import gate_event
from harness.preaction.owner import OwnerConfig
from harness.preaction.records import HoldStore, seal
from harness.preaction.verify import verify_store
from harness.preaction.witness import (HEAD_SCHEMA, check_heads, export_head, run_witness,
                                       transcript_calls, transcript_join)
from tests.preaction_fixtures import call, ctx

NOW = "2026-10-01T12:10:00Z"
OLD, RECENT = "2026-10-01T12:00:00Z", "2026-10-01T12:09:50Z"


def _claude_line(tool_id, name, ts, thinking=False):
    content = [{"type": "tool_use", "id": tool_id, "name": name, "input": {}}]
    if thinking:
        content.insert(0, {"type": "thinking", "thinking": "id toolu_FAKE type tool_use"})
    return {"type": "assistant", "timestamp": ts, "message": {"role": "assistant",
                                                              "content": content}}


def _codex_line(call_id, name, ts):
    return {"timestamp": ts, "type": "response_item",
            "payload": {"type": "function_call", "call_id": call_id, "name": name,
                        "arguments": "{}"}}


def _write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _hooked(home, tool_use_id, **args):
    c = call("Read", harness="claude-code", path_id="E11", **args)
    c = type(c)(**{**c.__dict__, "tool_use_id": tool_use_id})
    return gate_event(home, c, ctx(run_id="s1"), OwnerConfig())


def test_hooked_calls_join_and_match(tmp_path):
    home = tmp_path / "home"
    _hooked(home, "toolu_A", file_path="/work/repo/a.py")
    t = _write(tmp_path / "s.jsonl", [_claude_line("toolu_A", "Read", OLD)])
    assert transcript_join(home, [t], now=NOW)["verdict"] == "MATCH"


def test_skipped_hook_is_drift_after_the_grace_window(tmp_path):
    home = tmp_path / "home"
    _hooked(home, "toolu_A", file_path="/work/repo/a.py")
    t = _write(tmp_path / "s.jsonl", [_claude_line("toolu_A", "Read", OLD),
                                      _claude_line("toolu_B", "Bash", OLD),
                                      _claude_line("toolu_C", "Bash", RECENT)])
    out = transcript_join(home, [t], now=NOW, grace_seconds=60)
    assert out["verdict"] == "DRIFT"
    assert out["orphans"] == [{"id": "toolu_B", "name": "Bash"}]
    assert out["within_grace"] == 1


def test_codex_rollout_shape_joins(tmp_path):
    home = tmp_path / "home"
    _hooked(home, "call_1", file_path="/work/repo/a.py")
    t = _write(tmp_path / "rollout.jsonl", [_codex_line("call_1", "shell", OLD),
                                            _codex_line("call_2", "shell", OLD)])
    out = transcript_join(home, [t], now=NOW)
    assert out["verdict"] == "DRIFT" and [o["id"] for o in out["orphans"]] == ["call_2"]


def test_thinking_items_are_never_read_as_calls(tmp_path):
    t = _write(tmp_path / "s.jsonl", [_claude_line("toolu_A", "Read", OLD, thinking=True),
                                      {"type": "response_item", "timestamp": OLD,
                                       "payload": {"type": "reasoning", "id": "rs_1"}}])
    calls, _, _ = transcript_calls(t)
    assert [c["id"] for c in calls] == ["toolu_A"]


def test_no_readable_transcript_is_unverifiable(tmp_path):
    out = transcript_join(tmp_path / "home", [tmp_path / "missing.jsonl"], now=NOW)
    assert out["verdict"] == "UNVERIFIABLE"


def test_consistent_rewrite_after_head_export_is_drift(tmp_path):
    home, wit = tmp_path / "home", tmp_path / "witness"
    _hooked(home, "toolu_A", file_path="/work/repo/a.py")
    _hooked(home, "toolu_B", file_path="/work/repo/b.py")
    export_head(home, wit, clock=lambda: NOW)
    assert check_heads(home, wit)["verdict"] == "MATCH"
    # Rewrite the store end to end with a valid chain: the store verifier alone
    # cannot see it, the exported head can.
    store = HoldStore(home)
    recs = store.read_all()
    recs[1]["tool"] = "Write"
    prev = recs[0]["seal"]["hex"]
    recs[1]["prev_record_sha256"] = prev
    recs[1].pop("seal")
    seal(recs[1])
    store.path.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in recs),
                          encoding="utf-8")
    # The store verifier alone reads the rewritten chain as MATCH (seals and
    # links hold); only the exported head shows the rewrite.
    assert verify_store(home)["internal_verdict"] == "MATCH"
    heads = check_heads(home, wit)
    assert heads["verdict"] == "DRIFT"
    assert heads["findings"] == [{"cause": "EXPORTED_HEAD_REWRITTEN", "head_seq": 2}]


def test_truncated_store_is_drift(tmp_path):
    home, wit = tmp_path / "home", tmp_path / "witness"
    _hooked(home, "toolu_A", file_path="/work/repo/a.py")
    export_head(home, wit, clock=lambda: NOW)
    (home / "records.jsonl").write_text("", encoding="utf-8")
    assert check_heads(home, wit)["findings"][0]["cause"] == "EXPORTED_HEAD_MISSING"


def test_no_exported_head_is_unverifiable(tmp_path):
    assert check_heads(tmp_path / "home", tmp_path / "w")["verdict"] == "UNVERIFIABLE"


def test_hook_exports_a_head_at_every_stop(tmp_path):
    home, wit = tmp_path / "home", tmp_path / "witness"
    owner = OwnerConfig(witness_dir=str(wit), head_export_every=1000)
    c = call("Bash", harness="claude-code", path_id="E11", command="git push --force origin main")
    g = gate_event(home, c, ctx(run_id="s1"), owner)
    assert not g.run
    heads = [r for r in HoldStore(wit).read_all() if r["schema"] == HEAD_SCHEMA]
    assert len(heads) == 1 and heads[0]["head_seq"] == 1
    assert verify_store(wit)["internal_verdict"] in ("MATCH", "UNVERIFIABLE")


def test_witness_record_is_sealed_and_cli_exit_codes(tmp_path):
    home, wit = tmp_path / "home", tmp_path / "witness"
    _hooked(home, "toolu_A", file_path="/work/repo/a.py")
    export_head(home, wit, clock=lambda: NOW)
    good = _write(tmp_path / "good.jsonl", [_claude_line("toolu_A", "Read", OLD)])
    rec = run_witness(home, wit, [good], now=NOW)
    assert rec["verdict"] == "MATCH" and rec["seal"]["hex"]
    bad = _write(tmp_path / "bad.jsonl", [_claude_line("toolu_Z", "Bash", OLD)])
    out = io.StringIO()
    code = cli.main(["witness", "--home", str(home), "--witness-dir", str(wit),
                     "--transcripts", str(bad), "--now", NOW], stdout=out, stderr=io.StringIO())
    assert code == 1 and json.loads(out.getvalue())["verdict"] == "DRIFT"
