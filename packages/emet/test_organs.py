#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""test_organs.py - behavior proof for organs.py perception + impedance.

Boundary 1 (SPEC s.2, s.6.1): the impedance gate reports the re-derivable FACT
of a clean operator revert path - REVERTIBLE / NOT_REVERTIBLE - never a
permission token. These tests pin that fact-reporting behavior and the governed
perception tokens (UNCHANGED / DRIFTED / NEW / GONE).
"""
import os, sys, json, tempfile, shutil, subprocess, unittest, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
ORGANS = os.path.join(HERE, "organs.py")

class OrgansBehavior(unittest.TestCase):
    def setUp(self):
        # A plain temp dir, NOT a git repo: git ls-files --error-unmatch fails
        # here, so a present-but-untracked file has no VCS revert path.
        self.tmp = tempfile.mkdtemp(prefix="organs_test_")
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_organs(self, args):
        p = subprocess.run([sys.executable, ORGANS] + args, cwd=self.tmp,
                           capture_output=True, text=True)
        return p.returncode, p.stdout

    def test_gate_absent_path_is_revertible_exit_0(self):
        # An absent path: the revert is to delete the new file, so the FACT is a
        # clean revert path exists -> REVERTIBLE, exit 0.
        code, out = self.run_organs(["gate", os.path.join(self.tmp, "nope.txt")])
        self.assertRegex(out, r"(?m)^REVERTIBLE ")
        self.assertRegex(out, r"(?m)^gate=REVERTIBLE\b")
        self.assertEqual(code, 0)

    def test_gate_present_untracked_is_not_revertible_exit_1(self):
        # A present file in a non-git dir has no VCS revert path -> the FACT is
        # NOT_REVERTIBLE, a NEGATIVE FINDING -> exit 1 (SPEC s.5). No permission
        # token is emitted, and exit 1 is a fact, not a denial (Boundary 1/4).
        f = os.path.join(self.tmp, "present.txt")
        with open(f, "wb") as fh:
            fh.write(b"untracked_bytes\n")
        code, out = self.run_organs(["gate", f])
        self.assertRegex(out, r"(?m)^NOT_REVERTIBLE ")
        self.assertRegex(out, r"(?m)^gate=NOT_REVERTIBLE\b")
        self.assertEqual(code, 1)

    def test_observe_emits_new_unchanged_drifted_and_gone(self):
        # A manifest covering: an unknown path (NEW), a matching hash (UNCHANGED),
        # a changed file (DRIFTED), and an absent file (GONE). Exit 1 (SPEC s.5)
        # since the baseline changed (a negative finding).
        match = os.path.join(self.tmp, "match.txt")
        drift = os.path.join(self.tmp, "drift.txt")
        fresh = os.path.join(self.tmp, "fresh.txt")
        gone = os.path.join(self.tmp, "gone.txt")
        with open(match, "wb") as fh: fh.write(b"alpha\n")
        with open(drift, "wb") as fh: fh.write(b"beta\n")
        with open(fresh, "wb") as fh: fh.write(b"gamma\n")
        # manifest knows match (current hash), drift (stale hash), and gone
        # (absent); it does NOT know fresh, which therefore reads NEW.
        man = {
            "at": "no-head",
            "artifacts": {
                os.path.normpath(match): hashlib.sha256(b"alpha\n").hexdigest(),
                os.path.normpath(drift): hashlib.sha256(b"NOT-beta\n").hexdigest(),
                os.path.normpath(gone): hashlib.sha256(b"x\n").hexdigest(),
            },
        }
        manifest = os.path.join(self.tmp, "m.json")
        with open(manifest, "w", encoding="utf-8") as fh:
            json.dump(man, fh)
        code, out = self.run_organs(["observe", manifest, fresh, match, drift, gone])
        self.assertRegex(out, r"(?m)^NEW ")
        self.assertRegex(out, r"(?m)^UNCHANGED ")
        self.assertRegex(out, r"(?m)^DRIFTED ")
        self.assertRegex(out, r"(?m)^GONE ")
        self.assertEqual(code, 1)

    def test_gate_json_envelope(self):
        # --json emits one canonical envelope; the gate FACT (REVERTIBLE/
        # NOT_REVERTIBLE) is carried as verdict, exit 1 for NOT_REVERTIBLE, and
        # the closed lattice holds (no authority token).
        import json
        f = os.path.join(self.tmp, "present.txt")
        with open(f, "wb") as fh:
            fh.write(b"untracked\n")
        code, out = self.run_organs(["gate", "--json", f])
        env = json.loads(out)
        self.assertEqual(env["command"], "gate")
        self.assertEqual(env["verdict"], "NOT_REVERTIBLE")
        self.assertEqual(env["exit_code"], 1)
        self.assertEqual(code, 1)
        for tok in ("TRUSTED", "APPROVED", "SAFE", "AUTHORIZED"):
            self.assertNotIn(tok, json.dumps(env))

if __name__ == "__main__":
    unittest.main(verbosity=2)
