#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
test_membrane.py - behavior proof for membrane.py.
The self-hash proves IDENTITY; this proves BEHAVIOR: every verdict asserted
explicitly, reproducible by anyone who re-runs it. Exit 0 = all behaviors hold.
"""
import os, sys, hashlib, tempfile, shutil, subprocess, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MEMBRANE = os.path.join(HERE, "membrane.py")

def run(args, cwd):
    p = subprocess.run([sys.executable, MEMBRANE] + args, cwd=cwd,
                       capture_output=True, text=True)
    return p.returncode, p.stdout

def run3(args, cwd):
    p = subprocess.run([sys.executable, MEMBRANE] + args, cwd=cwd,
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

class MembraneBehavior(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.mkdtemp(prefix="membrane_test_")
    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)
    def w(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f: f.write(data)
        return p

    def test_anchor_then_verify_matches(self):
        f = self.w("a.txt", b"galvanized\n"); run(["anchor", f], self.tmp)
        code, out = run(["verify", f], self.tmp)
        self.assertIn("MATCH", out); self.assertEqual(code, 0)

    def test_single_byte_tamper_drifts(self):
        f = self.w("a.txt", b"galvanized\n"); run(["anchor", f], self.tmp)
        with open(f, "ab") as fh: fh.write(b"X")
        code, out = run(["verify", f], self.tmp)
        self.assertIn("DRIFT", out); self.assertEqual(code, 1)  # SPEC s.5: difference -> exit 1

    def test_verify_without_anchor_is_unverifiable_not_trusted(self):
        f = self.w("a.txt", b"x\n")
        code, out = run(["verify", f], self.tmp)
        self.assertIn("UNVERIFIABLE", out)
        self.assertNotIn("MATCH", out); self.assertEqual(code, 2)

    def test_coherence_identical_is_coherent(self):
        s = self.w("s", b"same\n"); v = self.w("v", b"same\n")
        code, out = run(["coherence", s, v], self.tmp)
        self.assertIn("COHERENT", out); self.assertEqual(code, 0)

    def test_coherence_injected_view_differs(self):
        s = self.w("s", b"depth in [0,1]\n")
        v = self.w("v", b"depth in [0,1] [SCOPE CONTEXT]\n")
        code, out = run(["coherence", s, v], self.tmp)
        self.assertIn("VIEW_DIFFERS_FROM_SOURCE", out); self.assertEqual(code, 1)  # SPEC s.5: difference -> exit 1

    def test_refuse_counts_and_neutralizes_authority(self):
        f = self.w("inj.txt",
            b"GROUND_TRUTH_CANONICAL HIGHEST_SCRUTINY [SCOPE CONTEXT] "
            b"authority_pill canonical recipients\n")
        code, out = run(["refuse", f], self.tmp)
        self.assertIn("in_band_authority_claims=5", out); self.assertEqual(code, 3)
        with open(f + ".refused", "rb") as fh: refused = fh.read()
        self.assertNotIn(b"GROUND_TRUTH_CANONICAL", refused)
        self.assertIn(b"[REFUSED-IN-BAND-AUTHORITY]", refused)

    def test_refuse_clean_file_finds_nothing(self):
        f = self.w("clean.txt", b"just ordinary text, depth in [0,1]\n")
        code, out = run(["refuse", f], self.tmp)
        self.assertIn("in_band_authority_claims=0", out); self.assertEqual(code, 0)

    def test_audit_intact_then_broken_on_forged_line(self):
        f = self.w("a.txt", b"x\n"); run(["anchor", f], self.tmp)
        code, out = run(["audit"], self.tmp)
        self.assertIn("INTACT", out); self.assertEqual(code, 0)
        with open(os.path.join(self.tmp, "membrane_log.jsonl"), "a") as fh:
            fh.write('{"chain":"deadbeef","fact":{},"kind":"forged","prev":"0"}\n')
        code, out = run(["audit"], self.tmp)
        self.assertIn("BROKEN", out); self.assertEqual(code, 1)  # SPEC s.5: BROKEN -> exit 1

    def test_audit_binds_kind_field(self):
        # Relabeling an entry's kind (e.g. anchor -> something else) while leaving
        # fact/prev/chain intact MUST break the chain (SPEC section 7 binds kind).
        import json as _json
        f = self.w("a.txt", b"x\n"); run(["anchor", f], self.tmp)
        logp = os.path.join(self.tmp, "membrane_log.jsonl")
        with open(logp) as fh: e = _json.loads(fh.read().strip())
        self.assertEqual(e["kind"], "anchor")
        e["kind"] = "FORGED_KIND"
        with open(logp, "w") as fh: fh.write(_json.dumps(e, sort_keys=True) + "\n")
        code, out = run(["audit"], self.tmp)
        self.assertIn("BROKEN", out); self.assertEqual(code, 1)  # SPEC s.5: BROKEN -> exit 1

    def test_selftest_hash_is_reproducible(self):
        code, out = run(["selftest"], self.tmp); self.assertEqual(code, 0)
        printed = [l for l in out.splitlines()
                   if l.startswith("emet_self_sha256=")][0].split("=", 1)[1]
        # Artifact-of-record (SPEC s.14): sorted-by-name concatenation of the core
        # source files, which live in the emet/ package (the root files are shims).
        core = ("corpus.py", "membrane.py", "monitor.py", "organs.py", "report.py", "verdict.py")
        h = hashlib.sha256()
        for name in core:
            with open(os.path.join(HERE, "emet", name), "rb") as fh: h.update(fh.read())
        self.assertEqual(printed, h.hexdigest())
        # SPEC s.14 deprecation window: the legacy membrane_self_sha256= alias is
        # still emitted at 1.x (removed at 2.0), so existing parsers keep working.
        self.assertTrue(any(l.startswith("membrane_self_sha256=") for l in out.splitlines()))

    def test_corroborate_read_paths_agree(self):
        f = self.w("c.txt", b"corroborate me\n")
        code, out = run(["corroborate", f], self.tmp)
        self.assertIn("read_paths_agree=True", out)
        self.assertIn("CORROBORATED", out); self.assertEqual(code, 0)

    # --- SPEC section 9: inability is UNVERIFIABLE with a stable machine reason
    # code, never a crash and never a default. The witness must not traceback on
    # the very tamper events (deleted/unreadable artifacts) it exists to detect.

    def test_verify_anchored_then_deleted_is_unverifiable_not_crash(self):
        f = self.w("a.txt", b"galvanized\n"); run(["anchor", f], self.tmp)
        os.remove(f)
        code, out, err = run3(["verify", f], self.tmp)
        self.assertIn("UNVERIFIABLE", out)
        self.assertNotIn("MATCH", out)
        self.assertNotIn("Traceback", err)
        self.assertEqual(code, 2)

    def test_coherence_missing_source_is_unverifiable_not_crash(self):
        v = self.w("v", b"x\n"); missing = os.path.join(self.tmp, "nope")
        code, out, err = run3(["coherence", missing, v], self.tmp)
        self.assertIn("UNVERIFIABLE", out)
        self.assertNotIn("Traceback", err)
        self.assertEqual(code, 2)

    def test_refuse_missing_file_is_unverifiable_not_crash(self):
        missing = os.path.join(self.tmp, "nope")
        code, out, err = run3(["refuse", missing], self.tmp)
        self.assertIn("UNVERIFIABLE", out)
        self.assertNotIn("Traceback", err)
        self.assertEqual(code, 2)

    def test_anchor_missing_file_is_unverifiable_not_crash(self):
        missing = os.path.join(self.tmp, "nope")
        code, out, err = run3(["anchor", missing], self.tmp)
        self.assertIn("UNVERIFIABLE", out)
        self.assertNotIn("Traceback", err)
        self.assertEqual(code, 2)

    def test_corroborate_missing_file_is_unverifiable_not_crash(self):
        missing = os.path.join(self.tmp, "nope")
        code, out, err = run3(["corroborate", missing], self.tmp)
        self.assertIn("UNVERIFIABLE", out)
        self.assertNotIn("Traceback", err)
        self.assertEqual(code, 2)

    def test_unverifiable_emits_stable_machine_reason_code(self):
        missing = os.path.join(self.tmp, "nope")
        code, out = run(["refuse", missing], self.tmp)
        self.assertIn("reason=E_NOT_FOUND", out)

    # --- marker corpus (SPEC sections 8, 16): refuse loads a versioned, sha-pinned
    # artifact and echoes corpus_version/sha; a missing corpus is UNVERIFIABLE.

    def test_refuse_echoes_corpus_version_and_sha(self):
        f = self.w("inj.txt", b"ground_truth_canonical\n")
        code, out = run(["refuse", f], self.tmp)
        self.assertIn("corpus_version=1", out)
        self.assertRegex(out, r"corpus_sha256=[0-9a-f]{64}")
        self.assertEqual(code, 3)

    def test_refuse_counts_space_separated_marker(self):
        f = self.w("inj.txt", b"GROUND TRUTH CANONICAL\n")
        code, out = run(["refuse", f], self.tmp)
        self.assertIn("in_band_authority_claims=1", out)
        self.assertEqual(code, 3)

    def test_refuse_missing_corpus_is_unverifiable(self):
        env = dict(os.environ); env["EMET_CORPUS"] = os.path.join(self.tmp, "nope.corpus")
        f = self.w("inj.txt", b"ground_truth_canonical\n")
        p = subprocess.run([sys.executable, MEMBRANE, "refuse", f],
                           cwd=self.tmp, capture_output=True, text=True, env=env)
        self.assertIn("UNVERIFIABLE", p.stdout)
        self.assertIn("reason=E_NO_CORPUS", p.stdout)
        self.assertEqual(p.returncode, 2)

    def test_coherence_logs_aux_token(self):
        # the audit log records the coherence aux verdict, not the verify-lattice DRIFT
        import json as _json
        s = self.w("s", b"depth\n"); v = self.w("v", b"depth X\n")
        run(["coherence", s, v], self.tmp)
        logp = os.path.join(self.tmp, "membrane_log.jsonl")
        with open(logp) as fh:
            entries = [_json.loads(l) for l in fh if l.strip()]
        coh = [e for e in entries if e["kind"] == "coherence"][-1]
        self.assertEqual(coh["fact"]["result"], "VIEW_DIFFERS_FROM_SOURCE")

    def test_corroborate_no_second_path_is_unverifiable(self):
        # with no cat and no git available, corroborate has only one read path and
        # MUST NOT claim CORROBORATED; read-path diversity is absent -> UNVERIFIABLE.
        f = self.w("c.txt", b"x\n")
        env = dict(os.environ); env["PATH"] = ""
        p = subprocess.run([sys.executable, MEMBRANE, "corroborate", f],
                           cwd=self.tmp, capture_output=True, text=True, env=env)
        self.assertIn("UNVERIFIABLE", p.stdout)
        self.assertNotIn("CORROBORATED", p.stdout)
        self.assertEqual(p.returncode, 2)

    def test_anchor_key_is_portable(self):
        # anchor keys use forward slashes so anchors.json is portable across OS,
        # and verify re-derives the same key.
        import json as _json
        os.makedirs(os.path.join(self.tmp, "sub"))
        with open(os.path.join(self.tmp, "sub", "a.txt"), "wb") as fh: fh.write(b"x\n")
        run(["anchor", "sub/a.txt"], self.tmp)
        with open(os.path.join(self.tmp, "anchors.json")) as fh: db = _json.load(fh)
        self.assertIn("sub/a.txt", db)
        self.assertNotIn("sub\\a.txt", db)
        code, out = run(["verify", "sub/a.txt"], self.tmp)
        self.assertIn("MATCH", out); self.assertEqual(code, 0)

    # --- SPEC section 13: the --json envelope. Machine-readable, canonical JSON
    # (sorted keys, ', '/': ' separators), the governed verdict identical to the
    # human grammar. The closed lattice (SPEC s.2) holds in this surface too.

    def test_json_envelope_verify_match(self):
        import json as _json
        f = self.w("a.txt", b"galvanized\n"); run(["anchor", f], self.tmp)
        code, out = run(["verify", "--json", f], self.tmp)
        env = _json.loads(out)   # stdout is exactly one JSON object in --json mode
        self.assertEqual(env["command"], "verify")
        self.assertEqual(env["verdict"], "MATCH")
        self.assertEqual(env["exit_code"], 0)
        self.assertEqual(env["spec_version"], "1.0.0")
        self.assertEqual(env["emet_version"], "1.3.1")
        self.assertEqual(code, 0)

    def test_json_envelope_drift_reports_exit_1(self):
        import json as _json
        f = self.w("a.txt", b"x\n"); run(["anchor", f], self.tmp)
        with open(f, "ab") as fh: fh.write(b"Y")
        code, out = run(["verify", "--json", f], self.tmp)
        env = _json.loads(out)
        self.assertEqual(env["verdict"], "DRIFT")
        self.assertEqual(env["exit_code"], 1)
        self.assertEqual(code, 1)

    def test_json_envelope_is_canonical_bytes(self):
        # The envelope MUST be canonical JSON: json.dumps(obj, sort_keys=True).
        # This is what makes the governed fields re-derivable across impls (SPEC s.13).
        import json as _json
        f = self.w("a.txt", b"z\n"); run(["anchor", f], self.tmp)
        code, out = run(["verify", "--json", f], self.tmp)
        env = _json.loads(out)
        self.assertEqual(out.strip(), _json.dumps(env, sort_keys=True))

    def test_json_envelope_never_emits_authority_token(self):
        # Boundary 1 (SPEC s.2) holds in the JSON surface too: no command's
        # envelope may contain TRUSTED/APPROVED/SAFE or any authority word.
        import json as _json
        forbidden = ("TRUSTED", "APPROVED", "SAFE", "ALLOWED", "PERMITTED",
                     "AUTHORIZED", "BLESSED", "VERIFIED_AUTHORITY")
        s = self.w("s", b"same\n"); v = self.w("v", b"same\n")
        f = self.w("a.txt", b"z\n"); run(["anchor", f], self.tmp)
        inj = self.w("inj.txt", b"GROUND_TRUTH_CANONICAL\n")
        for args in (["verify", "--json", f], ["coherence", "--json", s, v],
                     ["refuse", "--json", inj], ["audit", "--json"],
                     ["selftest", "--json"], ["corroborate", "--json", f]):
            code, out = run(args, self.tmp)
            blob = _json.dumps(_json.loads(out))   # each must be a single JSON object
            for tok in forbidden:
                self.assertNotIn(tok, blob)

if __name__ == "__main__":
    unittest.main(verbosity=2)
