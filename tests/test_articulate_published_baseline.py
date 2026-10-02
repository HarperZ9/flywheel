"""Accepted release host-edit payload and its local approval boundary, stdlib-only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from harness import lane_tool_policy as policy
from harness.lanes_registry import LANES

ROOT = Path(__file__).resolve().parents[1]


class ArticulateAcceptedBaselineTests(unittest.TestCase):
    def test_accepted_host_protocol_is_the_bundled_source(self):
        row = next(json.loads(line) for line in (
            ROOT / "packaging/python-lane-payloads.jsonl").read_text(
                encoding="utf-8").splitlines() if json.loads(line)["lane"] == "articulate")
        self.assertEqual(LANES["articulate"].version, "0.6.0")
        self.assertEqual(row["owner_commit"], "36f7e9f1f027f400b4839ec7394d64823ed1ac1d")
        self.assertEqual(row["owner_tag"], "v0.6.0")
        self.assertEqual(row["owner_describe"], "v0.6.0")
        self.assertTrue({"edit_plan", "edit_submit"}.issubset(row["mcp"]["static_tool_names"]))
        self.assertTrue({"edit_plan", "edit_submit"}.issubset(
            row["component_descriptor"]["allowed_tools"]))

    def test_host_edit_is_local_and_needs_no_separate_account(self):
        for tool in ("edit_plan", "edit_submit"):
            with self.subTest(tool=tool):
                entry = policy.tool_policy("articulate", tool)
                self.assertIsNotNone(entry)
                self.assertEqual((entry.tier, entry.effect, entry.needs), ("T1", "read", ()))
                self.assertIn(tool, policy.admitted_tools("articulate"))

    def test_legacy_editors_still_require_explicit_approval(self):
        for tool in ("judge", "fix", "polish"):
            with self.subTest(tool=tool):
                entry = policy.tool_policy("articulate", tool)
                self.assertEqual((entry.tier, entry.effect), ("T2", "spend"))
                self.assertNotIn(tool, policy.admitted_tools("articulate"))

    def test_staged_host_protocol_preserves_protected_spans_and_claim_features(self):
        source = Path(os.environ.get("FLYWHEEL_ARTICULATE_SOURCE", str(
            ROOT / "build/python-lane-sources/articulate-v0.6.0")))
        if not (source / "src/articulate/local_mcp.py").is_file():
            self.skipTest("stage the manifest-pinned Articulate source first")
        # The stage verifier binds the exercised bytes to the committed row.
        from scripts.stage_python_lane_sources import _load_rows, _verify_manifest
        row = _load_rows(ROOT / "packaging/python-lane-payloads.jsonl")["articulate"]
        _verify_manifest(row, source)
        code = '''
import json, sys
sys.path.insert(0, sys.argv[1])
def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.system', 'os.posix_spawn'):
        raise AssertionError('host edit attempted external I/O: ' + event)
sys.addaudithook(audit)
from articulate import local_mcp
def call(name, arguments):
    response = local_mcp.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                'params': {'name': name, 'arguments': arguments}})
    result = response['result']
    assert not result.get('isError'), result
    return json.loads(result['content'][0]['text'])
original = 'We tested 14 files. Read the report.'
rewrite = 'Read the report. We tested 14 files.'
plan = call('edit_plan', {'text': original})
assert plan['status'] == 'host_edit_required' and plan['backend'] == 'host'
assert plan['attempts'] == []
accepted = call('edit_submit', {'text': original, 'rewrite': rewrite, 'plan_id': plan['plan_id']})
assert accepted['text'] == rewrite and accepted['refused'] == []
assert accepted['receipt']['backend'] == 'host' and accepted['attempts'] == []
refused = call('edit_submit', {'text': original, 'rewrite': original.replace('14', '15'),
                              'plan_id': plan['plan_id']})
assert refused['text'] == original and refused['refused']
assert 'semantic equivalence' in accepted['receipt']['does_not_prove']
claims = 'The change may help some users. It does not prove safety.'
plan = call('edit_plan', {'text': claims})
positive = 'The change may help some users, and it does not prove safety.'
result = call('edit_submit', {'text': claims, 'rewrite': positive, 'plan_id': plan['plan_id']})
assert result['text'] == positive and result['refused'] == []
for before, after, kind in [('may', 'will', 'modal'), ('some', 'all', 'scope'),
                            ('does not', 'does', 'negation')]:
    result = call('edit_submit', {'text': claims, 'rewrite': claims.replace(before, after),
                                 'plan_id': plan['plan_id']})
    assert result['text'] == claims and result['refused'], (kind, result)
    assert any(kind in reason for refusal in result['refused'] for reason in refusal['reasons'])
quoted = 'The record says "reviewed". Read https://example.org/source.'
plan = call('edit_plan', {'text': quoted})
for candidate in [quoted.replace('"reviewed"', '"verified"'),
                  quoted.replace('/source', '/other')]:
    result = call('edit_submit', {'text': quoted, 'rewrite': candidate, 'plan_id': plan['plan_id']})
    assert result['text'] == quoted and result['refused']
print(json.dumps({'host_edit': 'PASS', 'changed_number': 'REFUSED',
                  'claim_features': 'REFUSED', 'quote_url': 'REFUSED', 'external_io': 'NONE'}))
'''
        result = subprocess.run([sys.executable, "-S", "-c", code, str(source / "src")],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            "host_edit": "PASS", "changed_number": "REFUSED", "claim_features": "REFUSED",
            "quote_url": "REFUSED", "external_io": "NONE"})


if __name__ == "__main__":
    unittest.main()
