#!/usr/bin/env python3
"""Build the sample receipt bundle that ships in plugins/flywheel-verify/examples.

The bundle exists so a person trying the plugin, or a directory reviewer, can run
`verify_bundle` on something real without building one first. Its receipts are
made-up demonstration records: the hashes inside them name nothing, and the
README says so. One receipt carries an Ed25519 signature from a key generated for
this run and then discarded; the other is unsigned, so the tool's signature
counts show both states.

    python scripts/build_verify_plugin_examples.py [--out DIR]

Needs PyNaCl or cryptography for the one signature; verifying needs neither.
The output is committed as data, and tests/test_verify_plugin.py checks that it
verifies. Rerunning this makes a new key, so the bytes change each run.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.bundle import pack_bundle                                  # noqa: E402
from harness.receipt import Receipt                                     # noqa: E402
from harness.receipt_fields import (Budget, Denominator, EvidenceKind,   # noqa: E402
                                    Tier)
from harness.receipt_sign import ed25519_attach, unsigned               # noqa: E402
from harness.verdict import Attribution, Verdict                        # noqa: E402

DEFAULT_OUT = ROOT / "plugins" / "flywheel-verify" / "examples" / "bundle"
DEMO = "sha256:" + "0" * 64


def _receipt(objective: str) -> Receipt:
    den = Denominator(attempts=4, group_size=4, oracle_calls_consumed=4, hits=1,
                      undecided=0, unverifiable=0, parse_failures=0, timeouts=0,
                      tokens_in=0, tokens_out=0, cache_hit_tokens=0, tasks_proposed=1,
                      tasks_filtered_out=0, retries=0, oracle_feedback_visible=False,
                      filter_id="demo.none", filter_hash=DEMO, filter_is_learned=False)
    budget = Budget(wall_seconds_limit=60, tokens_limit=0, retries_limit=0,
                    exhausted=False)
    return Receipt(
        criterion_id="demo.sample-bundle", criterion_version=1, criterion_sha256=DEMO,
        family="demo", family_instance_id=f"demo-{objective}", generator_id="demo",
        generator_seed=0, candidate_sha256=DEMO, prompt_hash=DEMO,
        checker_module="checker/sample_checker.py", checker_source_sha256=DEMO,
        executes_candidate_code=False, oracle_qa_card_hash="demo",
        held_out_agreement="AGREE", evidence_kind=EvidenceKind.CONSTRUCTIVE,
        tier=Tier.CONSTRUCTION_CERTIFICATE, verdict=Verdict.PASS,
        attribution=Attribution.CANDIDATE, objective=objective,
        incumbent_objective=objective, incumbent_source="demo",
        coverage={"predicate_exact": True, "search_space_enumerated": True,
                  "enumerated_fraction": "1", "stop_reason": "complete",
                  "guarantee_weakens_above": None},
        raw_stdout_sha256="0" * 64, analysis_script_sha256=DEMO,
        model_ref="demo", base_weights_digest="", harness_version="demo",
        denominator=den, budget=budget)


def _signed(receipt: Receipt) -> dict:
    message = receipt.claim_sha256().encode()
    try:
        from nacl.signing import SigningKey
        key = SigningKey.generate()
        signature, public = bytes(key.sign(message).signature), bytes(key.verify_key)
    except ImportError:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        key = Ed25519PrivateKey.generate()
        signature = key.sign(message)
        public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return ed25519_attach(receipt, signature, public, key_id="demo-key").to_dict()


def build(out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    root = _pack(out)
    # pack_bundle writes the manifest in text mode, so a Windows build gets CRLF
    # there while every hashed file is LF. The manifest is not in its own file
    # list, so verification is the same either way; LF keeps the sample's bytes
    # the same on every platform.
    manifest = root / "manifest.json"
    manifest.write_bytes(manifest.read_bytes().replace(b"\r\n", b"\n"))
    return root


def _pack(out: Path) -> Path:
    return pack_bundle(
        out, envelopes=[_signed(_receipt("21")), unsigned(_receipt("22"))],
        criterion={"criterion_id": "demo.sample-bundle", "version": 1,
                   "note": "Demonstration bundle. These receipts name no real run."},
        checker_sources={"sample_checker.py": (
            '"""Demonstration checker. It is shipped to be read, never run."""\n\n\n'
            "def check(value: int) -> bool:\n"
            "    return value in (21, 22)\n")},
        qa_card={"schema": "flywheel.oracle-qa-card/v2", "passed": True,
                 "note": "Demonstration card with no measured rate."},
        tree_head={"schema": "flywheel.tree-head/v1", "size": 2, "root": DEMO})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    print(build(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
