#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
test_witness_receipt_cross_lang.py - the wave-2 cross-implementation gate for the
portable witness receipt (SPEC s.17).

Proves PARITY, not just per-impl correctness: the Python reference, the Rust port,
and the Node.js port emit a BYTE-IDENTICAL receipt_id for the same
subject/verdict/spec/issued_at, agree on every check verdict (valid / tampered /
unverifiable), detect subject drift, verify each other's HMAC signatures, never
emit an authority token, and re-verify a receipt produced by a DIFFERENT
implementation with zero shared state (portability, s.17).

The can-it-FAIL negatives are the point: a verifier that always returned
RECEIPT_VALID would be a certificate of authenticity, which violates the
facts-only boundary. Each negative asserts the verifier actually FAILS on a
tampered / drifted / unverifiable input.

Go is intentionally excluded: receipt/check are not yet ported to impl/go
(reported honestly, not faked). An impl whose toolchain is absent is skipped.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MEMBRANE = os.path.join(HERE, "membrane.py")
RUST_SRC = os.path.join(HERE, "impl", "rust", "emet.rs")
JS_SRC = os.path.join(HERE, "impl", "js", "emet.js")

FIXED_NOW = "2026-07-02T12:34:56Z"


def _which(name):
    return shutil.which(name)


def _build_rust():
    """Build the Rust impl if cargo/rustc is available; return the binary path or
    None. Prefer an already-built release binary; else compile with rustc -O."""
    exe = ".exe" if os.name == "nt" else ""
    release = os.path.join(HERE, "impl", "rust", "target", "release", "emet" + exe)
    if os.path.exists(release):
        return release
    if _which("cargo"):
        r = subprocess.run(["cargo", "build", "--release"],
                           cwd=os.path.join(HERE, "impl", "rust"),
                           capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(release):
            return release
    if _which("rustc"):
        out = os.path.join(tempfile.gettempdir(), "emet_xlang_rust" + exe)
        r = subprocess.run(["rustc", "-O", RUST_SRC, "-o", out],
                           capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(out):
            return out
    return None


RUST_BIN = _build_rust()
NODE_BIN = _which("node")


# --- per-impl driver: each returns (returncode, stdout) for a CLI invocation ---
class Impl:
    def __init__(self, name, argv_prefix, available):
        self.name = name
        self.argv_prefix = argv_prefix
        self.available = available

    def run(self, args, cwd, stdin=None, env_extra=None):
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)
        # Inject the fixed issued_at for the ports (Python emit_receipt is exercised
        # via the library seam; the port CLIs read EMET_RECEIPT_NOW).
        env.setdefault("EMET_RECEIPT_NOW", FIXED_NOW)
        p = subprocess.run(self.argv_prefix + args, cwd=cwd, input=stdin,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stdout, p.stderr


IMPLS = [
    Impl("python", [sys.executable, MEMBRANE], True),
    Impl("rust", [RUST_BIN] if RUST_BIN else None, RUST_BIN is not None),
    Impl("node", [NODE_BIN, JS_SRC] if NODE_BIN else None, NODE_BIN is not None),
]
ACTIVE = [i for i in IMPLS if i.available]

# A parity assertion over a SINGLE impl is vacuously true (a set of one id has
# length one), so this suite only proves cross-language parity when >= 2 impls
# are present. Locally an absent toolchain is skipped gracefully. In CI the
# guarantee this wave exists to prove MUST actually be exercised, so setting
# EMET_REQUIRE_CROSS_LANG=1 turns a missing port into a hard failure rather than
# a silent vacuous pass.
REQUIRED = {"python", "rust", "node"}


def setUpModule():
    if os.environ.get("EMET_REQUIRE_CROSS_LANG"):
        active_names = {i.name for i in ACTIVE}
        missing = REQUIRED - active_names
        if missing:
            raise RuntimeError(
                "EMET_REQUIRE_CROSS_LANG is set but these impls are not active "
                "(toolchain missing or build failed): "
                + ", ".join(sorted(missing))
                + ". Cross-lang parity cannot be proven; refusing a vacuous pass."
            )


class CrossLangReceipt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xlang_receipt_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def w(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def verify_envelope(self, name, data):
        """anchor + verify --json (via the Python reference) to get a canonical
        command envelope every impl can mint a receipt from."""
        self.w(name, data)
        subprocess.run([sys.executable, MEMBRANE, "anchor", name],
                       cwd=self.tmp, capture_output=True, text=True)
        p = subprocess.run([sys.executable, MEMBRANE, "verify", name, "--json"],
                           cwd=self.tmp, capture_output=True, text=True)
        return p.stdout

    def emit_via(self, impl, envelope, env_extra=None):
        """Emit a receipt from an envelope via one impl's CLI; return the parsed
        receipt dict. Python is driven via its own receipt --from-json path too, so
        every impl goes through the same CLI contract."""
        code, out, err = impl.run(["receipt", "--from-json", "-"], cwd=self.tmp,
                                  stdin=envelope, env_extra=env_extra)
        self.assertEqual(code, 0, f"{impl.name} receipt emit failed: {err}")
        return json.loads(out)

    def check_via(self, impl, receipt_path, recompute=False, env_extra=None):
        args = ["check", receipt_path]
        if recompute:
            args.append("--recompute-from-paths")
        return impl.run(args, cwd=self.tmp, env_extra=env_extra)

    # ---- group 1: emit parity - byte-identical receipt_id across impls --------

    def test_receipt_id_is_byte_identical_across_impls(self):
        # CAN-IT-FAIL #1: same subject/verdict/spec/issued_at -> identical 64-hex id.
        env = self.verify_envelope("a.txt", b"hello world\n")
        ids = {}
        for impl in ACTIVE:
            r = self.emit_via(impl, env)
            self.assertEqual(len(r["receipt_id"]), 64)
            self.assertTrue(all(c in "0123456789abcdef" for c in r["receipt_id"]))
            ids[impl.name] = r["receipt_id"]
        # every impl agrees on the content address
        self.assertEqual(len(set(ids.values())), 1,
                         f"receipt_id diverged across impls: {ids}")

    def test_witness_block_is_per_impl_but_id_is_not(self):
        # The witness identity legitimately differs per impl; the address does not.
        env = self.verify_envelope("a.txt", b"hello world\n")
        witnesses = {}
        ids = set()
        for impl in ACTIVE:
            r = self.emit_via(impl, env)
            witnesses[impl.name] = r["witness"]["implementation"]
            ids.add(r["receipt_id"])
        self.assertEqual(len(ids), 1)
        # each active impl names itself distinctly
        self.assertEqual(len(set(witnesses.values())), len(ACTIVE), witnesses)

    # ---- group 2: check verdicts - valid / tampered / unverifiable -----------

    def test_untouched_receipt_is_valid_everywhere(self):
        env = self.verify_envelope("a.txt", b"hello world\n")
        r = self.emit_via(ACTIVE[0], env)
        self.w_receipt("r.json", r)
        for impl in ACTIVE:
            code, out, _e = self.check_via(impl, "r.json")
            self.assertEqual(code, 0, impl.name)
            self.assertIn("RECEIPT_VALID", out, impl.name)

    def test_flipped_id_is_tampered_everywhere(self):
        # CAN-IT-FAIL #2: tampering flips the id and every impl reports TAMPERED.
        env = self.verify_envelope("a.txt", b"hello world\n")
        r = self.emit_via(ACTIVE[0], env)
        first = r["receipt_id"][0]
        r["receipt_id"] = ("1" if first == "0" else "0") + r["receipt_id"][1:]
        self.w_receipt("t.json", r)
        for impl in ACTIVE:
            code, out, _e = self.check_via(impl, "t.json")
            self.assertEqual(code, 1, impl.name)
            self.assertIn("RECEIPT_TAMPERED", out, impl.name)

    def test_tampered_governed_field_is_tampered_everywhere(self):
        # CAN-IT-FAIL #2b: mutate a governed field (verdict) without recomputing id.
        env = self.verify_envelope("a.txt", b"hello world\n")
        r = self.emit_via(ACTIVE[0], env)
        r["verdict_record"][0]["verdict"] = "DRIFT"  # id left stale on purpose
        self.w_receipt("t.json", r)
        for impl in ACTIVE:
            code, out, _e = self.check_via(impl, "t.json")
            self.assertEqual(code, 1, impl.name)
            self.assertIn("RECEIPT_TAMPERED", out, impl.name)

    def test_malformed_receipt_is_unverifiable_everywhere(self):
        # CAN-IT-FAIL #6: malformed JSON is UNVERIFIABLE (exit 2), never a traceback.
        with open(os.path.join(self.tmp, "bad.json"), "w", encoding="utf-8") as f:
            f.write("{not valid json")
        for impl in ACTIVE:
            code, out, err = self.check_via(impl, "bad.json")
            self.assertEqual(code, 2, f"{impl.name}: {err}")
            self.assertIn("RECEIPT_UNVERIFIABLE", out, impl.name)
            # stable reason code / token, never a stack trace
            self.assertNotIn("Traceback", out + err, impl.name)
            self.assertNotIn("panicked", (out + err).lower(), impl.name)

    # ---- group 3: subject re-derivation - drift + missing --------------------

    def test_subject_drift_detected_everywhere(self):
        # CAN-IT-FAIL #4: change the subject bytes; recompute -> TAMPERED.
        env = self.verify_envelope("a.txt", b"hello world\n")
        r = self.emit_via(ACTIVE[0], env)
        self.w_receipt("r.json", r)
        self.w("a.txt", b"totally different bytes\n")
        for impl in ACTIVE:
            code, out, _e = self.check_via(impl, "r.json", recompute=True)
            self.assertEqual(code, 1, impl.name)
            self.assertIn("RECEIPT_TAMPERED", out, impl.name)

    def test_missing_subject_on_recompute_is_unverifiable_everywhere(self):
        # CAN-IT-FAIL #5: a deleted subject is UNVERIFIABLE (not TAMPERED).
        env = self.verify_envelope("a.txt", b"hello world\n")
        r = self.emit_via(ACTIVE[0], env)
        self.w_receipt("r.json", r)
        os.remove(os.path.join(self.tmp, "a.txt"))
        for impl in ACTIVE:
            code, out, _e = self.check_via(impl, "r.json", recompute=True)
            self.assertEqual(code, 2, impl.name)
            self.assertIn("RECEIPT_UNVERIFIABLE", out, impl.name)

    def test_unchanged_subject_on_recompute_stays_valid_everywhere(self):
        env = self.verify_envelope("a.txt", b"hello world\n")
        r = self.emit_via(ACTIVE[0], env)
        self.w_receipt("r.json", r)
        for impl in ACTIVE:
            code, out, _e = self.check_via(impl, "r.json", recompute=True)
            self.assertEqual(code, 0, impl.name)
            self.assertIn("RECEIPT_VALID", out, impl.name)

    # ---- group 4: signature verification (Python + Rust + Node) --------------

    def test_signed_receipt_verifies_cross_impl(self):
        # CAN-IT-FAIL #3: a receipt signed by one impl verifies under all impls with
        # the correct key, fails with a wrong key, and is UNVERIFIABLE with no key.
        env = self.verify_envelope("a.txt", b"hello world\n")
        signer = ACTIVE[0]
        r = self.emit_via(signer, env, env_extra={"EMET_RECEIPT_SIGNING_KEY": "shared-secret"})
        self.assertIsNotNone(r["signature"])
        self.w_receipt("s.json", r)
        for impl in ACTIVE:
            good = self.check_via(impl, "s.json", env_extra={"EMET_RECEIPT_SIGNING_KEY": "shared-secret"})
            self.assertEqual(good[0], 0, f"{impl.name} correct-key")
            self.assertIn("RECEIPT_VALID", good[1], impl.name)
            bad = self.check_via(impl, "s.json", env_extra={"EMET_RECEIPT_SIGNING_KEY": "wrong-key"})
            self.assertEqual(bad[0], 1, f"{impl.name} wrong-key")
            self.assertIn("RECEIPT_TAMPERED", bad[1], impl.name)
            nokey = self.check_via(impl, "s.json", env_extra={"EMET_RECEIPT_SIGNING_KEY": ""})
            self.assertEqual(nokey[0], 2, f"{impl.name} no-key")
            self.assertIn("RECEIPT_UNVERIFIABLE", nokey[1], impl.name)

    def test_signatures_are_byte_identical_across_impls(self):
        # The HMAC construction is the same across impls, so the signature hex over
        # the same body + key matches (Rust's hand-rolled HMAC == Python/Node).
        env = self.verify_envelope("a.txt", b"hello world\n")
        sigs = {}
        for impl in ACTIVE:
            r = self.emit_via(impl, env, env_extra={"EMET_RECEIPT_SIGNING_KEY": "shared-secret"})
            sigs[impl.name] = r["signature"]
        self.assertEqual(len(set(sigs.values())), 1, f"signatures diverged: {sigs}")

    # ---- group 5: authority-token absence ------------------------------------

    def test_no_authority_token_in_any_receipt(self):
        # CAN-IT-FAIL #7: no TRUSTED/APPROVED/SAFE/... in any emitted receipt.
        env = self.verify_envelope("a.txt", b"hello world\n")
        forbidden = ("TRUSTED", "APPROVED", "SAFE", "ALLOWED", "PERMITTED",
                     "AUTHORIZED", "BLESSED", "VERIFIED_AUTHORITY")
        for impl in ACTIVE:
            r = self.emit_via(impl, env, env_extra={"EMET_RECEIPT_SIGNING_KEY": "k"})
            blob = json.dumps(r)
            for tok in forbidden:
                self.assertNotIn(tok, blob, f"{impl.name} leaked {tok}")

    # ---- group 6: portability - emit in one impl, verify in the others -------

    def test_receipt_is_portable_across_impls(self):
        # CAN-IT-FAIL #8: a receipt produced by producer P re-verifies VALID under
        # EVERY other impl, with zero shared anchor store / log / key.
        env = self.verify_envelope("a.txt", b"portable bytes\n")
        for producer in ACTIVE:
            r = self.emit_via(producer, env)
            self.w_receipt("p.json", r)
            for verifier in ACTIVE:
                code, out, _e = self.check_via(verifier, "p.json")
                self.assertEqual(code, 0,
                                 f"{producer.name}->{verifier.name} not VALID")
                self.assertIn("RECEIPT_VALID", out)

    def test_unsigned_receipt_null_signature_verifies_on_content_address(self):
        # CAN-IT-FAIL #9: an unsigned (signature: null) receipt verifies on the
        # content address alone under every impl (signature is optional, s.17.4).
        env = self.verify_envelope("a.txt", b"hello world\n")
        r = self.emit_via(ACTIVE[0], env)
        self.assertIsNone(r["signature"])
        self.w_receipt("u.json", r)
        for impl in ACTIVE:
            code, out, _e = self.check_via(impl, "u.json")  # no key in env
            self.assertEqual(code, 0, impl.name)
            self.assertIn("RECEIPT_VALID", out, impl.name)

    # --- helper: write a receipt dict as canonical JSON to tmp ---------------
    def w_receipt(self, name, receipt):
        # sort_keys reproduces the canonical byte form; check re-derives regardless.
        with open(os.path.join(self.tmp, name), "w", encoding="utf-8") as f:
            json.dump(receipt, f, sort_keys=True, separators=(", ", ": "))


def _print_active():
    names = ", ".join(i.name for i in ACTIVE)
    skipped = [i.name for i in IMPLS if not i.available]
    msg = "cross-lang receipt: active impls = [" + names + "]"
    if skipped:
        msg += "  skipped (toolchain absent) = [" + ", ".join(skipped) + "]"
    print(msg, file=sys.stderr)


if __name__ == "__main__":
    _print_active()
    unittest.main()
