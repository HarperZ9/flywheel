#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""test_monitor.py - behavior proof for monitor.py corpus handling."""
import os, sys, json, tempfile, shutil, subprocess, unittest, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
MONITOR = os.path.join(HERE, "monitor.py")

class MonitorBehavior(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="monitor_test_")
        self.target = os.path.join(self.tmp, "t.txt")
        with open(self.target, "wb") as f:
            f.write(b"ground_truth_canonical\n")
        h = hashlib.sha256(b"ground_truth_canonical\n").hexdigest()
        self.manifest = os.path.join(self.tmp, "m.json")
        with open(self.manifest, "w", encoding="utf-8") as f:
            json.dump({self.target: h}, f)
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
    def run_mon(self, args, env=None):
        p = subprocess.run([sys.executable, MONITOR] + args, cwd=self.tmp,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stdout

    def test_report_echoes_corpus_version_and_sha(self):
        code, out = self.run_mon(["report", self.manifest])
        self.assertIn("corpus_version=1", out)
        self.assertRegex(out, r"corpus_sha256=[0-9a-f]{64}")

    def test_report_missing_corpus_is_unverifiable(self):
        env = dict(os.environ); env["EMET_CORPUS"] = os.path.join(self.tmp, "nope.corpus")
        code, out = self.run_mon(["report", self.manifest], env=env)
        self.assertIn("UNVERIFIABLE", out)
        self.assertIn("reason=E_NO_CORPUS", out)
        self.assertEqual(code, 2)

    def test_report_governs_match_drift_missing_and_baseline_changed(self):
        # The governed monitor tokens (SPEC s.2): a manifest mixing a matching,
        # a drifted, and a missing file emits per-file MATCH / DRIFT / MISSING and
        # the per-baseline CHANGED summary, with exit 1 (SPEC s.5: a negative finding).
        mfile = os.path.join(self.tmp, "match.txt"); dfile = os.path.join(self.tmp, "drift.txt")
        gone = os.path.join(self.tmp, "gone.txt")
        with open(mfile, "wb") as f: f.write(b"alpha\n")
        with open(dfile, "wb") as f: f.write(b"beta\n")
        man = {mfile: hashlib.sha256(b"alpha\n").hexdigest(),
               dfile: hashlib.sha256(b"NOT-beta\n").hexdigest(),
               gone: hashlib.sha256(b"x\n").hexdigest()}
        mp = os.path.join(self.tmp, "mix.json")
        with open(mp, "w", encoding="utf-8") as f: json.dump(man, f)
        code, out = self.run_mon(["report", mp])
        self.assertRegex(out, r"(?m)^MATCH ")
        self.assertRegex(out, r"(?m)^DRIFT ")
        self.assertRegex(out, r"(?m)^MISSING ")
        self.assertIn("baseline=CHANGED", out)
        self.assertEqual(code, 1)

    def test_report_all_match_is_baseline_intact(self):
        code, out = self.run_mon(["report", self.manifest])
        self.assertIn("baseline=INTACT", out)
        self.assertEqual(code, 0)

    def test_report_json_envelope(self):
        # --json emits one canonical envelope carrying the governed baseline verdict.
        import json
        code, out = self.run_mon(["report", "--json", self.manifest])
        env = json.loads(out)
        self.assertEqual(env["command"], "report")
        self.assertIn(env["verdict"], ("INTACT", "CHANGED", "UNVERIFIABLE"))
        self.assertEqual(env["spec_version"], "1.0.0")
        for tok in ("TRUSTED", "APPROVED", "SAFE", "AUTHORIZED"):
            self.assertNotIn(tok, json.dumps(env))

if __name__ == "__main__":
    unittest.main(verbosity=2)
