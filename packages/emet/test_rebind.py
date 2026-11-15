#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
test_rebind.py - behavior proof for stripped-credential rebind (SPEC s.18).

The C2PA failure mode is an artifact whose embedded provenance was stripped. EMET
never bound to embedded metadata, so it rebinds by re-deriving the content hash of
the naked bytes and looking it up in a known-anchor manifest. This proves the
BEHAVIOR of that rebind, verdict by verdict, and - critically - proves the
verifier can FAIL: a rebind that always said MATCH would be a certificate of
authenticity, which violates the facts-only boundary. Every verdict is asserted
explicitly; UNVERIFIABLE is proven to be the honest default for unknown bytes.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from emet import rebind as rb
from emet.report import canonical
from emet.verdict import LATTICE, VerdictError, governed

HERE = os.path.dirname(os.path.abspath(__file__))
MEMBRANE = os.path.join(HERE, "membrane.py")

FIXED_NOW = "2026-07-02T00:00:00Z"


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def make_manifest(records):
    return rb.build_manifest(records, issued_at=FIXED_NOW)


class RebindLibrary(unittest.TestCase):
    """Library-level proof: rebind() and rebind_manifest() over in-memory bytes."""

    def setUp(self):
        self.original = b"original raw image bytes\n"
        self.digest = sha256_hex(self.original)
        self.manifest = make_manifest(
            [{"digest": self.digest, "identity": "photo-2026-001"}])

    # --- the three honest verdicts ---------------------------------------

    def test_stripped_bytes_rebind_to_known_anchor_is_match(self):
        # The credential is stripped; the RAW BYTES are unchanged. Re-deriving the
        # content hash and looking it up rebinds the artifact -> MATCH.
        verdict, detail, digest = rb.rebind_manifest(self.original, self.manifest)
        self.assertEqual(verdict, "MATCH")
        self.assertIn("photo-2026-001", detail)
        self.assertEqual(digest, self.digest)

    def test_claimed_identity_with_wrong_bytes_is_drift(self):
        # The caller asserts the artifact IS photo-2026-001 (an out-of-band claim a
        # stripped file no longer carries), but the bytes hash differently. That is
        # a confirmed substitution -> DRIFT, not merely unknown.
        forged = b"substituted bytes\n"
        verdict, detail, _ = rb.rebind_manifest(
            forged, self.manifest, claim="photo-2026-001")
        self.assertEqual(verdict, "DRIFT")
        self.assertIn("photo-2026-001", detail)

    def test_unknown_bytes_no_claim_is_unverifiable_never_trusted(self):
        # No anchor records these bytes and no claim was made. The honest default
        # is UNVERIFIABLE - an unknown artifact is unknown, never a pass.
        verdict, detail, _ = rb.rebind_manifest(b"who knows\n", self.manifest)
        self.assertEqual(verdict, "UNVERIFIABLE")
        self.assertNotIn("MATCH", verdict)
        self.assertIn("E_NO_ANCHOR", detail)

    # --- the sharp edges --------------------------------------------------

    def test_right_bytes_wrong_claimed_name_is_drift(self):
        # The bytes ARE a known anchor, but the caller claims a DIFFERENT identity.
        # Right bytes, wrong asserted name -> DRIFT (a mislabelling is a difference).
        verdict, detail, _ = rb.rebind_manifest(
            self.original, self.manifest, claim="some-other-id")
        self.assertEqual(verdict, "DRIFT")
        self.assertIn("photo-2026-001", detail)

    def test_matching_claim_and_bytes_is_still_match(self):
        verdict, _detail, _ = rb.rebind_manifest(
            self.original, self.manifest, claim="photo-2026-001")
        self.assertEqual(verdict, "MATCH")

    def test_tampered_manifest_id_refuses_to_rebind(self):
        # A doctored manifest cannot ground any judgement. EMET refuses to rebind
        # against corruption -> UNVERIFIABLE, never a MATCH off a forged anchor set.
        bad = dict(self.manifest)
        bad["manifest_id"] = "0" * 64
        verdict, detail, _ = rb.rebind_manifest(self.original, bad)
        self.assertEqual(verdict, "UNVERIFIABLE")
        self.assertIn("E_MANIFEST_TAMPERED", detail)

    def test_manifest_without_id_is_unverifiable(self):
        bad = dict(self.manifest)
        del bad["manifest_id"]
        verdict, detail, _ = rb.rebind_manifest(self.original, bad)
        self.assertEqual(verdict, "UNVERIFIABLE")
        self.assertIn("E_MANIFEST_UNVERIFIABLE", detail)

    def test_rebind_never_emits_an_authority_token(self):
        # The verdict is drawn from the closed primary lattice; it can never be
        # TRUSTED/APPROVED/etc. Prove the channel refuses an authority word.
        for v, _d, _h in (
            rb.rebind_manifest(self.original, self.manifest),
            rb.rebind_manifest(b"x\n", self.manifest),
        ):
            self.assertIn(v, LATTICE)
        with self.assertRaises(VerdictError):
            governed(LATTICE, "TRUSTED")

    # --- the manifest content address ------------------------------------

    def test_manifest_id_is_content_address_of_records(self):
        body = {k: v for k, v in self.manifest.items() if k != "manifest_id"}
        self.assertEqual(self.manifest["manifest_id"],
                         sha256_hex(canonical(body).encode()))

    def test_ambiguous_anchor_is_a_build_error(self):
        # One digest cannot stand for two identities; an ambiguous anchor set is
        # refused at build time rather than silently resolving to one of them.
        with self.assertRaises(ValueError):
            make_manifest([
                {"digest": self.digest, "identity": "photo-a"},
                {"digest": self.digest, "identity": "photo-b"},
            ])

    def test_manifest_digest_is_case_normalized(self):
        # An anchor recorded with an upper-case digest still rebinds lower-case
        # re-derived bytes (sha256 hex is compared case-insensitively).
        m = make_manifest([{"digest": self.digest.upper(), "identity": "id"}])
        verdict, _d, _h = rb.rebind_manifest(self.original, m)
        self.assertEqual(verdict, "MATCH")


class RebindCLI(unittest.TestCase):
    """Command-level proof: the `rebind` subcommand, exit codes, and receipts."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rebind_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def w(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def emet(self, args, env_extra=None):
        env = dict(os.environ)
        env["EMET_REBIND_NOW"] = FIXED_NOW
        if env_extra:
            env.update(env_extra)
        p = subprocess.run([sys.executable, MEMBRANE] + args, cwd=self.tmp,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stdout, p.stderr

    def build_manifest_file(self, pairs):
        code, out, err = self.emet(["rebind", "--build-manifest"] + pairs)
        self.assertEqual(code, 0, err)
        path = os.path.join(self.tmp, "manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(out)
        return path

    def test_build_manifest_then_rebind_stripped_copy_matches(self):
        self.w("photo.png", b"original raw image bytes\n")
        manifest = self.build_manifest_file(["photo.png=photo-2026-001"])
        # A stripped/re-encoded copy with identical content bytes but no credential.
        self.w("stripped.png", b"original raw image bytes\n")
        code, out, _ = self.emet(["rebind", "stripped.png", "--manifest", manifest])
        self.assertIn("result=MATCH", out)
        self.assertIn("photo-2026-001", out)
        self.assertEqual(code, 0)

    def test_rebind_wrong_bytes_with_claim_drifts_exit_1(self):
        self.w("photo.png", b"original raw image bytes\n")
        manifest = self.build_manifest_file(["photo.png=photo-2026-001"])
        self.w("forged.png", b"forged content\n")
        code, out, _ = self.emet(
            ["rebind", "forged.png", "--manifest", manifest,
             "--claim", "photo-2026-001"])
        self.assertIn("result=DRIFT", out)
        self.assertEqual(code, 1)

    def test_rebind_unknown_bytes_is_unverifiable_exit_2(self):
        self.w("photo.png", b"original raw image bytes\n")
        manifest = self.build_manifest_file(["photo.png=photo-2026-001"])
        self.w("unknown.png", b"never seen before\n")
        code, out, _ = self.emet(["rebind", "unknown.png", "--manifest", manifest])
        self.assertIn("result=UNVERIFIABLE", out)
        self.assertNotIn("result=MATCH", out)
        self.assertEqual(code, 2)

    def test_rebind_missing_naked_file_is_unverifiable(self):
        self.w("p", b"x\n")
        manifest = self.build_manifest_file(["p=id"])
        code, out, _ = self.emet(["rebind", "ghost.png", "--manifest", manifest])
        self.assertIn("UNVERIFIABLE", out)
        self.assertIn("E_NOT_FOUND", out)
        self.assertEqual(code, 2)

    def test_rebind_missing_manifest_is_unverifiable(self):
        self.w("naked.png", b"bytes\n")
        code, out, _ = self.emet(
            ["rebind", "naked.png", "--manifest", "no-such-manifest.json"])
        self.assertIn("UNVERIFIABLE", out)
        self.assertEqual(code, 2)

    def test_rebind_json_envelope_carries_governed_verdict(self):
        self.w("photo.png", b"original raw image bytes\n")
        manifest = self.build_manifest_file(["photo.png=photo-2026-001"])
        self.w("stripped.png", b"original raw image bytes\n")
        code, out, _ = self.emet(
            ["rebind", "stripped.png", "--manifest", manifest, "--json"])
        env = json.loads(out)
        self.assertEqual(env["command"], "rebind")
        self.assertEqual(env["verdict"], "MATCH")
        self.assertIn(env["verdict"], LATTICE)
        self.assertTrue(env["experimental"])
        self.assertEqual(env["exit_code"], 0)
        self.assertEqual(code, 0)

    def test_rebind_verdict_seals_into_a_portable_receipt(self):
        # The accountability layer rides underneath: a rebind FACT can be sealed
        # into a witness receipt (SPEC s.17) and re-checked offline, so the fact
        # travels off-machine where the stripped credential could not.
        self.w("photo.png", b"original raw image bytes\n")
        manifest = self.build_manifest_file(["photo.png=photo-2026-001"])
        self.w("stripped.png", b"original raw image bytes\n")
        _c, env_out, _ = self.emet(
            ["rebind", "stripped.png", "--manifest", manifest, "--json"])
        with open(os.path.join(self.tmp, "env.json"), "w", encoding="utf-8") as f:
            f.write(env_out)
        code, r_out, err = self.emet(
            ["receipt", "--from-json", "env.json"],
            env_extra={"EMET_RECEIPT_NOW": "2026-07-02T12:00:00Z"})
        self.assertEqual(code, 0, err)
        receipt = json.loads(r_out)
        self.assertEqual(receipt["verdict_record"][0]["command"], "rebind")
        self.assertEqual(receipt["verdict_record"][0]["verdict"], "MATCH")
        with open(os.path.join(self.tmp, "receipt.json"), "w", encoding="utf-8") as f:
            f.write(r_out)
        code, chk_out, _ = self.emet(["check", "receipt.json"])
        self.assertIn("RECEIPT_VALID", chk_out)
        self.assertEqual(code, 0)

    def test_rebind_writes_a_tamper_evident_log_entry(self):
        # The rebind rides on the existing accountability spine: it records to the
        # hash-chained log, which audits INTACT.
        self.w("photo.png", b"original raw image bytes\n")
        manifest = self.build_manifest_file(["photo.png=photo-2026-001"])
        self.w("stripped.png", b"original raw image bytes\n")
        self.emet(["rebind", "stripped.png", "--manifest", manifest])
        code, out, _ = self.emet(["audit"])
        self.assertIn("chain=INTACT", out)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
