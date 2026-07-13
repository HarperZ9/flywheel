"""test_tool_receipts.py — per-tool-call HMAC signing catches a forged result.

Success criteria:
  - a signed call verifies; tampering with output / ok / key fails verification.
  - the loop attaches a signature to each tool_result when a sign_key is given,
    and does not when it is not.
"""
from harness.local_loop import run_agent
from harness.local_tools import ToolExecutor, ToolResult
from harness.tool_receipts import (
    new_session_key,
    sign_call,
    sign_result,
    verify_call,
    verify_result,
)


def test_sign_and_verify_roundtrip():
    key = new_session_key()
    sig = sign_call(key, name="run", args={"cmd": "pytest"}, ok=True, rc=0, output="5 passed")
    assert verify_call(key, sig, name="run", args={"cmd": "pytest"}, ok=True, rc=0, output="5 passed")


def test_forged_result_fails_verification():
    key = new_session_key()
    sig = sign_call(key, name="run", args={"cmd": "pytest"}, ok=True, output="5 passed")
    assert not verify_call(key, sig, name="run", args={"cmd": "pytest"}, ok=True, output="1 failed")
    assert not verify_call(key, sig, name="run", args={"cmd": "pytest"}, ok=False, output="5 passed")


def test_wrong_key_fails():
    sig = sign_call(new_session_key(), name="x", args={}, ok=True)
    assert not verify_call(new_session_key(), sig, name="x", args={}, ok=True)


def test_sign_result_over_a_toolresult():
    key = new_session_key()
    r = ToolResult(name="read_file", args={"path": "a"}, ok=True, output="content")
    assert verify_result(key, sign_result(key, r), r)
    tampered = ToolResult(name="read_file", args={"path": "a"}, ok=True, output="TAMPERED")
    assert not verify_result(key, sign_result(key, r), tampered)


class _Stub:
    system = "you are an agent"

    def __init__(self, script):
        self.script = list(script)

    def send(self, message):
        return {"content": [{"text": self.script.pop(0) if self.script else "done"}]}


def test_loop_signs_tool_results_only_when_key_given(tmp_path):
    (tmp_path / "f.txt").write_text("hi", encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path))

    key = new_session_key()
    out = run_agent(_Stub(['TOOL list_dir {"path": "."}', "done"]), "list", ex,
                    max_steps=3, sign_key=key)
    sigs = [e.meta.get("sig") for e in out["ledger"].entries if e.kind == "tool_result"]
    assert sigs and all(sigs)                             # every tool_result is signed

    out2 = run_agent(_Stub(['TOOL list_dir {"path": "."}', "done"]), "list", ex, max_steps=3)
    assert all(e.meta.get("sig") is None for e in out2["ledger"].entries if e.kind == "tool_result")
