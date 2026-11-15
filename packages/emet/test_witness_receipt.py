#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
test_witness_receipt.py - behavior proof for the portable witness receipt.

The self-hash proves IDENTITY; this proves BEHAVIOR: a receipt content-addresses
itself, travels off the machine that made it, and re-derives on a DIFFERENT
machine with zero shared state. Every verdict is asserted explicitly, and the
can-it-FAIL negatives prove the verifier actually detects tampering and subject
drift - a receipt that always says RECEIPT_VALID would be a certificate of
authenticity, which violates the facts-only boundary.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from emet import witness_receipt as wr
from emet.report import canonical
from emet.verdict import RECEIPT, VerdictError, governed

HERE = os.path.dirname(os.path.abspath(__file__))
MEMBRANE = os.path.join(HERE, "membrane.py")

FIXED_NOW = "2026-07-02T12:34:56Z"


def sha256_hex(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


class ReceiptCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="receipt_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def w(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def anchor_and_verify(self, name, data):
        # Anchor a file then produce a verify --json envelope for it, in tmp.
        self.w(name, data)
        subprocess.run([sys.executable, MEMBRANE, "anchor", name],
                       cwd=self.tmp, capture_output=True, text=True)
        p = subprocess.run([sys.executable, MEMBRANE, "verify", name, "--json"],
                           cwd=self.tmp, capture_output=True, text=True)
        return json.loads(p.stdout)

    # --- format + content-addressing ------------------------------------

    def test_receipt_has_stable_format_tag(self):
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        self.assertEqual(r["format"], "emet-witness-receipt/v1")
        self.assertEqual(r["issued_at"], FIXED_NOW)

    def test_receipt_id_is_content_address_of_the_rest(self):
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        # Re-derive the id from the receipt minus id + signature + witness
        # (SPEC s.17.2: the per-implementation witness block is producer identity,
        # not a re-derivation-governed field, so it is excluded from the address).
        body = {k: v for k, v in r.items()
                if k not in ("receipt_id", "signature", "witness")}
        self.assertEqual(r["receipt_id"], sha256_hex(canonical(body).encode()))

    def test_witness_block_does_not_govern_the_content_address(self):
        # Cross-impl parity (SPEC s.17.2): mutating the per-implementation witness
        # identity must NOT change receipt_id, so a Python/Rust/Node receipt over
        # the same subject/verdict/spec/issued_at re-derives the SAME address.
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        original = r["receipt_id"]
        r["witness"] = {"implementation": "emet-rust-reference",
                        "spec_version": "1.0.0", "self_sha256": "deadbeef" * 8}
        self.assertEqual(wr.receipt_id_hash(r), original)
        # And check still says VALID: the id was computed over the addressed body.
        verdict, _detail = wr.check_receipt(r)
        self.assertEqual(verdict, "RECEIPT_VALID")

    def test_receipt_records_subject_digest_and_verdict(self):
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        want = sha256_hex(b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        self.assertEqual(r["subject"][0]["path"], "a.txt")
        self.assertEqual(r["subject"][0]["sha256"], want)
        self.assertEqual(r["verdict_record"][0]["verdict"], "MATCH")
        self.assertEqual(r["verdict_record"][0]["subject_index"], 0)
        self.assertEqual(r["verdict_record"][0]["command"], "verify")

    def test_receipt_pins_spec_version_and_self_hash(self):
        env = self.anchor_and_verify("a.txt", b"x\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        self.assertEqual(r["witness"]["spec_version"], "1.0.0")
        self.assertEqual(r["witness"]["implementation"], "emet-python-reference")
        self.assertEqual(len(r["witness"]["self_sha256"]), 64)

    def test_receipt_carries_no_authority_token(self):
        env = self.anchor_and_verify("a.txt", b"x\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        encoded = json.dumps(r)
        for tok in ("TRUSTED", "APPROVED", "SAFE", "AUTHORIZED", "PERMITTED"):
            self.assertNotIn(tok, encoded)

    def test_same_bytes_same_spec_rederives_same_receipt_id(self):
        # The re-derivation guarantee: same bytes + same spec + same corpus and
        # same issued_at -> byte-identical content address. Two isolated dirs.
        env1 = self.anchor_and_verify("a.txt", b"same bytes\n")
        r1 = wr.emit_receipt(env1, base_dir=self.tmp, now=FIXED_NOW)
        tmp2 = tempfile.mkdtemp(prefix="receipt_test2_")
        try:
            with open(os.path.join(tmp2, "a.txt"), "wb") as f:
                f.write(b"same bytes\n")
            subprocess.run([sys.executable, MEMBRANE, "anchor", "a.txt"],
                           cwd=tmp2, capture_output=True, text=True)
            p = subprocess.run([sys.executable, MEMBRANE, "verify", "a.txt", "--json"],
                               cwd=tmp2, capture_output=True, text=True)
            env2 = json.loads(p.stdout)
            r2 = wr.emit_receipt(env2, base_dir=tmp2, now=FIXED_NOW)
            self.assertEqual(r1["receipt_id"], r2["receipt_id"])
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    # --- load + round-trip ----------------------------------------------

    def test_load_roundtrips_a_written_receipt(self):
        env = self.anchor_and_verify("a.txt", b"round trip\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        path = os.path.join(self.tmp, "r.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(canonical(r))
        loaded = wr.load_receipt(path)
        self.assertEqual(loaded["receipt_id"], r["receipt_id"])

    # --- offline check: valid, tampered, unverifiable -------------------

    def test_check_untouched_receipt_is_valid(self):
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        verdict, _detail = wr.check_receipt(r)
        self.assertEqual(verdict, "RECEIPT_VALID")

    def test_check_malformed_receipt_is_unverifiable(self):
        verdict, _detail = wr.check_receipt({"not": "a receipt"})
        self.assertEqual(verdict, "RECEIPT_UNVERIFIABLE")

    # --- CAN-IT-FAIL #1: flipped receipt_id -> RECEIPT_TAMPERED ---------

    def test_flipped_receipt_id_is_tampered(self):
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        # Flip one hex digit of the stored id; the body no longer hashes to it.
        first = r["receipt_id"][0]
        flipped = ("1" if first == "0" else "0") + r["receipt_id"][1:]
        r["receipt_id"] = flipped
        verdict, detail = wr.check_receipt(r)
        self.assertEqual(verdict, "RECEIPT_TAMPERED")
        self.assertIn("receipt_id", detail)

    def test_tampered_verdict_field_breaks_the_id(self):
        # An attacker rewrites the recorded verdict from MATCH to something else
        # but cannot recompute a matching content address without the whole body.
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        r["verdict_record"][0]["verdict"] = "DRIFT"  # id left stale on purpose
        verdict, _detail = wr.check_receipt(r)
        self.assertEqual(verdict, "RECEIPT_TAMPERED")

    # --- CAN-IT-FAIL #2: subject bytes changed -> subject drift ---------

    def test_recompute_from_changed_bytes_detects_drift(self):
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        # Replace the subject's bytes entirely; its digest now diverges.
        self.w("a.txt", b"totally different bytes\n")
        verdict, detail = wr.check_receipt(r, base_dir=self.tmp, recompute=True)
        self.assertEqual(verdict, "RECEIPT_TAMPERED")
        self.assertIn("a.txt", detail)

    def test_recompute_matching_bytes_stays_valid(self):
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        verdict, _detail = wr.check_receipt(r, base_dir=self.tmp, recompute=True)
        self.assertEqual(verdict, "RECEIPT_VALID")

    def test_recompute_missing_subject_is_unverifiable(self):
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        os.remove(os.path.join(self.tmp, "a.txt"))
        verdict, detail = wr.check_receipt(r, base_dir=self.tmp, recompute=True)
        self.assertEqual(verdict, "RECEIPT_UNVERIFIABLE")
        self.assertIn("a.txt", detail)

    # --- optional signature (HMAC) --------------------------------------

    def test_signed_receipt_verifies_with_key(self):
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW,
                            signing_key=b"shared-secret")
        self.assertIsNotNone(r["signature"])
        verdict, _detail = wr.check_receipt(r, signing_key=b"shared-secret")
        self.assertEqual(verdict, "RECEIPT_VALID")

    def test_signed_receipt_wrong_key_is_tampered(self):
        env = self.anchor_and_verify("a.txt", b"hello world\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW,
                            signing_key=b"shared-secret")
        verdict, detail = wr.check_receipt(r, signing_key=b"wrong-key")
        self.assertEqual(verdict, "RECEIPT_TAMPERED")
        self.assertIn("signature", detail)

    def test_unsigned_receipt_has_null_signature(self):
        env = self.anchor_and_verify("a.txt", b"x\n")
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        self.assertIsNone(r["signature"])

    # --- verdict lattice governance -------------------------------------

    def test_receipt_verdicts_are_governed(self):
        for tok in ("RECEIPT_VALID", "RECEIPT_TAMPERED", "RECEIPT_UNVERIFIABLE"):
            self.assertEqual(governed(RECEIPT, tok), tok)

    def test_authority_token_refused_as_receipt_verdict(self):
        with self.assertRaises(VerdictError):
            governed(RECEIPT, "TRUSTED")


class ReceiptCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="receipt_cli_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_membrane(self, args, stdin=None):
        p = subprocess.run([sys.executable, MEMBRANE] + args, cwd=self.tmp,
                           capture_output=True, text=True, input=stdin)
        return p.returncode, p.stdout, p.stderr

    def w(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def test_receipt_help_exits_usage(self):
        code, out, err = self.run_membrane(["receipt", "--help"])
        self.assertEqual(code, 64)
        self.assertIn("receipt", (out + err).lower())

    def test_receipt_from_json_stdin_emits_receipt(self):
        self.w("t.txt", b"hello world\n")
        self.run_membrane(["anchor", "t.txt"])
        _c, verify_json, _e = self.run_membrane(["verify", "t.txt", "--json"])
        code, out, _err = self.run_membrane(["receipt", "--from-json", "-"],
                                            stdin=verify_json)
        self.assertEqual(code, 0)
        r = json.loads(out)
        self.assertEqual(r["format"], "emet-witness-receipt/v1")
        self.assertEqual(r["verdict_record"][0]["verdict"], "MATCH")

    def test_check_valid_receipt_exit_zero(self):
        self.w("t.txt", b"hello world\n")
        self.run_membrane(["anchor", "t.txt"])
        _c, verify_json, _e = self.run_membrane(["verify", "t.txt", "--json"])
        _c2, receipt_out, _e2 = self.run_membrane(["receipt", "--from-json", "-"],
                                                  stdin=verify_json)
        with open(os.path.join(self.tmp, "r.json"), "w", encoding="utf-8") as f:
            f.write(receipt_out)
        code, out, _err = self.run_membrane(["check", "r.json"])
        self.assertEqual(code, 0)
        self.assertIn("RECEIPT_VALID", out)

    def test_check_tampered_receipt_exit_one(self):
        self.w("t.txt", b"hello world\n")
        self.run_membrane(["anchor", "t.txt"])
        _c, verify_json, _e = self.run_membrane(["verify", "t.txt", "--json"])
        _c2, receipt_out, _e2 = self.run_membrane(["receipt", "--from-json", "-"],
                                                  stdin=verify_json)
        r = json.loads(receipt_out)
        first = r["receipt_id"][0]
        r["receipt_id"] = ("1" if first == "0" else "0") + r["receipt_id"][1:]
        with open(os.path.join(self.tmp, "r.json"), "w", encoding="utf-8") as f:
            json.dump(r, f)
        code, out, _err = self.run_membrane(["check", "r.json"])
        self.assertEqual(code, 1)
        self.assertIn("RECEIPT_TAMPERED", out)

    def test_check_recompute_changed_bytes_exit_one(self):
        self.w("t.txt", b"hello world\n")
        self.run_membrane(["anchor", "t.txt"])
        _c, verify_json, _e = self.run_membrane(["verify", "t.txt", "--json"])
        _c2, receipt_out, _e2 = self.run_membrane(["receipt", "--from-json", "-"],
                                                  stdin=verify_json)
        with open(os.path.join(self.tmp, "r.json"), "w", encoding="utf-8") as f:
            f.write(receipt_out)
        self.w("t.txt", b"changed\n")
        code, out, _err = self.run_membrane(["check", "r.json", "--recompute-from-paths"])
        self.assertEqual(code, 1)
        self.assertIn("RECEIPT_TAMPERED", out)

    def test_check_malformed_receipt_exit_two(self):
        with open(os.path.join(self.tmp, "bad.json"), "w", encoding="utf-8") as f:
            f.write("{not valid json")
        code, out, _err = self.run_membrane(["check", "bad.json"])
        self.assertEqual(code, 2)
        self.assertIn("RECEIPT_UNVERIFIABLE", out)

    def test_check_json_mode_emits_canonical_envelope(self):
        self.w("t.txt", b"hello world\n")
        self.run_membrane(["anchor", "t.txt"])
        _c, verify_json, _e = self.run_membrane(["verify", "t.txt", "--json"])
        _c2, receipt_out, _e2 = self.run_membrane(["receipt", "--from-json", "-"],
                                                  stdin=verify_json)
        with open(os.path.join(self.tmp, "r.json"), "w", encoding="utf-8") as f:
            f.write(receipt_out)
        code, out, _err = self.run_membrane(["check", "r.json", "--json"])
        env = json.loads(out)
        self.assertEqual(env["command"], "check")
        self.assertEqual(env["verdict"], "RECEIPT_VALID")
        self.assertEqual(env["exit_code"], 0)


class PortableAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="receipt_adapter_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def w(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def make_receipt(self, name, data):
        self.w(name, data)
        subprocess.run([sys.executable, MEMBRANE, "anchor", name],
                       cwd=self.tmp, capture_output=True, text=True)
        p = subprocess.run([sys.executable, MEMBRANE, "verify", name, "--json"],
                           cwd=self.tmp, capture_output=True, text=True)
        env = json.loads(p.stdout)
        r = wr.emit_receipt(env, base_dir=self.tmp, now=FIXED_NOW)
        path = os.path.join(self.tmp, "r.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(canonical(r))
        return path

    def test_adapter_check_valid(self):
        from adapters.witness_receipt_portable import check
        path = self.make_receipt("a.txt", b"hello world\n")
        verdict, exit_code, _detail = check(path)
        self.assertEqual(verdict, "RECEIPT_VALID")
        self.assertEqual(exit_code, 0)

    def test_adapter_check_recompute_drift(self):
        from adapters.witness_receipt_portable import check
        path = self.make_receipt("a.txt", b"hello world\n")
        self.w("a.txt", b"different\n")
        verdict, exit_code, _detail = check(path, base_dir=self.tmp, recompute=True)
        self.assertEqual(verdict, "RECEIPT_TAMPERED")
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
