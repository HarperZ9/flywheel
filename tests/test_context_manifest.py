"""The context manifest: what actually entered the model's window, provable
from the witnessed ledger. Reads carry the hash of the content the model
saw (the reproducibility key), tools are counted, and the provenance note
is load-bearing: this loop has no ambient context — every entry originates
from a witnessed tool call, which is the poisoning defense."""

import json

from harness.context_manifest import SCHEMA, context_manifest
from harness.local_session import SessionLedger


def _ledger():
    led = SessionLedger()
    led.append("user", "fix the bug")
    led.append("assistant", 'TOOL read_file {"path": "a.py"}')
    led.append("tool_call", 'read_file {"path": "a.py"}')
    led.append("tool_result", "def f():\n    return 1\n",
               {"tool": "read_file", "ok": True})
    led.append("tool_call", 'grep {"pattern": "f", "path": "."}')
    led.append("tool_result", "a.py:1: def f()", {"tool": "grep", "ok": True})
    return led


def test_manifest_hashes_what_the_model_saw():
    m = context_manifest(_ledger().entries, system="be careful",
                         goal="fix the bug")
    assert m["schema"] == SCHEMA
    assert m["reads"] == [{
        "path": "a.py",
        "content_sha256": m["reads"][0]["content_sha256"],
    }]
    assert len(m["reads"][0]["content_sha256"]) == 64
    assert m["tools"] == {"read_file": 1, "grep": 1}
    assert len(m["system_sha256"]) == 64
    assert len(m["goal_sha256"]) == 64
    assert "witnessed tool call" in m["note"]


def test_manifest_is_deterministic():
    a = context_manifest(_ledger().entries, system="s", goal="g")
    b = context_manifest(_ledger().entries, system="s", goal="g")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_the_run_doc_carries_the_manifest():
    from harness.local_loop import _done
    out = _done("answer", 2, _ledger(), system="s", goal="fix the bug")
    m = out["context_manifest"]
    assert m["schema"] == SCHEMA
    assert m["reads"][0]["path"] == "a.py"


def test_the_run_doc_pins_its_environment():
    """Import 2 from the landscape queue: acceptance re-runs in a NAMED
    environment. Every run doc carries the runtime identity."""
    from harness.local_loop import _done
    env = _done("a", 1, _ledger())["environment"]
    for key in ("python", "platform", "machine"):
        assert env[key], f"environment must name {key}"
