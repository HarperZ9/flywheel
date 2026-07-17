"""Line-level provenance, Agent-Trace shaped: every machine-authored hunk
is attributed — path, author, the hash of what the model wrote, the hunk
ranges where the diff format carries them, and the conversation checkpoint
the change came from. Honest nulls: an edit whose line numbers are unknown
says so instead of inventing spans."""

import json

from harness.provenance_trace import SCHEMA, provenance_trace


def _e(kind, content):
    return {"kind": kind, "content": content, "meta": {}}


PATCH = """\
--- a/billing/invoice.py
+++ b/billing/invoice.py
@@ -10,3 +10,5 @@
-def total(items):
+def total(items, tax_rate=0.0):
+    return sum(i.price for i in items) * (1 + tax_rate)
"""


def _entries():
    return [
        _e("tool_call", 'write_file ' + json.dumps(
            {"path": "new.py", "content": "x = 1\n"}, sort_keys=True)),
        _e("tool_call", 'edit_file ' + json.dumps(
            {"path": "old.py", "old": "a", "new": "b"}, sort_keys=True)),
        _e("tool_call", 'apply_patch ' + json.dumps(
            {"patch": PATCH}, sort_keys=True)),
    ]


def test_every_machine_hunk_is_attributed():
    doc = provenance_trace(_entries(), checkpoint="chk123",
                           author="model:ollama:qwen2.5:3b")
    assert doc["schema"] == SCHEMA
    assert doc["conversation"] == "chk123"
    rows = {r["path"]: r for r in doc["attributions"]}
    assert rows["new.py"]["author"] == "model:ollama:qwen2.5:3b"
    assert len(rows["new.py"]["content_sha256"]) == 64
    assert rows["new.py"]["hunks"] == [[1, 1]]  # whole new file, 1 line
    assert rows["old.py"]["hunks"] is None      # honest: spans unknown
    assert rows["billing/invoice.py"]["hunks"] == [[10, 14]]


def test_deterministic():
    a = provenance_trace(_entries(), checkpoint="c", author="m")
    b = provenance_trace(_entries(), checkpoint="c", author="m")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
