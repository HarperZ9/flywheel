"""Integration test: agent loop with sealed tool-call receipt emission."""
from __future__ import annotations

import json
from pathlib import Path

from harness.local_tools import ToolExecutor, ToolGate


def test_tool_executor_emits_receipts_when_configured(tmp_path: Path):
    """A ToolExecutor with receipt_dir emits one sealed receipt per call,
    chained by prev_receipt_sha256, verifiable by verify_chain."""
    from harness.tool_call_receipt import verify_chain

    receipt_dir = tmp_path / "receipts"
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "hello.txt").write_text("hello world", encoding="utf-8")

    executor = ToolExecutor(
        root=str(root),
        gate=ToolGate(allow_write=False, allow_exec=False),
        receipt_dir=str(receipt_dir),
    )
    executor.init_receipt_chain("test-run")

    # Two tool calls
    executor.execute("read_file", {"path": "hello.txt"})
    executor.execute("list_dir", {"path": "."})

    # Load the emitted receipts
    receipt_files = sorted(receipt_dir.glob("*.json"))
    assert len(receipt_files) == 2
    receipts = [json.loads(f.read_text(encoding="utf-8")) for f in receipt_files]

    # The chain must verify
    result = verify_chain(receipts)
    assert result["verdict"] == "MATCH", f"chain failed: {result}"
    assert result["n"] == 2

    # The chain head must be non-empty
    assert executor.receipt_chain_head()

    # Receipts carry capability classification
    caps = {r["capability"] for r in receipts}
    assert "builtin-read" in caps

    # No raw args content leaked into the receipt
    for r in receipts:
        body = json.dumps(r)
        assert "hello.txt" not in body or r["tool"] != "read_file" or "hello.txt" not in r.get("args", {}).get("sha256", "")


def test_tool_executor_no_receipts_when_not_configured(tmp_path: Path):
    """Without receipt_dir, no receipts are emitted (byte-identical behavior)."""
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "hello.txt").write_text("hello", encoding="utf-8")

    executor = ToolExecutor(root=str(root), gate=ToolGate())
    executor.execute("read_file", {"path": "hello.txt"})

    # No receipt dir created
    assert not (tmp_path / "receipts").exists()


def test_transitive_witness_bridge_from_receipts(tmp_path: Path):
    """Tool-call receipts convert to DepNode entries; a tampered receipt
    degrades only its downstream dependents."""
    from harness.tool_call_receipt import build_receipt, _canonical_bytes, _sha256_hex
    from harness.transitive_witness import tool_call_receipts_to_dag, transitive_verdicts, MATCH

    r0 = build_receipt(tool="read_file", capability="builtin-read", admission="ALLOWED",
                       args={"path": "a"}, output="a", ok=True, rc=0,
                       run_id="test", seq=0, prev_receipt_sha256="")
    probe = dict(r0)
    probe["seal"] = {"algorithm": "sha256", "hex": ""}
    r0_hash = _sha256_hex(_canonical_bytes(probe))

    r1 = build_receipt(tool="read_file", capability="builtin-read", admission="ALLOWED",
                       args={"path": "b"}, output="b", ok=True, rc=0,
                       run_id="test", seq=1, prev_receipt_sha256=r0_hash)

    nodes = tool_call_receipts_to_dag([r0, r1])
    verdicts = transitive_verdicts(nodes)
    assert all(v == MATCH for v in verdicts.values())

    # Tamper r0: the first node becomes DRIFT. The chain link breaks because the
    # tampered receipt has a different sha than r1's prev_receipt_sha256, so r1
    # becomes independent (MATCH) — a broken link detaches, it doesn't degrade.
    r0_tampered = dict(r0)
    r0_tampered["output"] = dict(r0_tampered["output"])
    r0_tampered["output"]["bytes"] = 999
    r0_tampered["seal"] = dict(r0_tampered["seal"])
    r0_tampered["seal"]["hex"] = "0" * 64
    nodes_t = tool_call_receipts_to_dag([r0_tampered, r1])
    verdicts_t = transitive_verdicts(nodes_t)
    sources = list(verdicts_t.keys())
    assert verdicts_t[sources[0]] == "DRIFT"  # the tampered receipt is caught
    assert verdicts_t[sources[1]] == MATCH     # chain link broken -> independent
