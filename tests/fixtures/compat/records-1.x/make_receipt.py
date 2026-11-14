"""make_receipt.py -- seal one receipt for the gate record, with the installed release.

Run by the installed 1.x release in its own throwaway environment, after
`flywheel gate DIR` wrote DIR/gate_envelope.json. It builds a receipt with
that release's own `harness.receipt.Receipt` and writes DIR/receipt.json. The
field values come from the gate envelope beside it and from the fixed table
below, so every release seals the same claim in its own schema version.

    python -I make_receipt.py DIR

Standard library plus the installed `harness` package. Nothing here is
imported by the test suite; the README beside this file has the commands.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from importlib import metadata
from pathlib import Path

from harness.receipt import Receipt
from harness.receipt_fields import Budget, Denominator, EvidenceKind, Tier
from harness.verdict import Attribution, Verdict


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _values(envelope: dict, version: str) -> dict:
    return dict(
        criterion_id="matmul.2x2x2.rank7", criterion_version=1,
        criterion_sha256=_sha("matmul.2x2x2.rank7/v1"),
        family="matmul", family_instance_id=envelope["task_id"],
        generator_id=envelope["model_ref"], generator_seed=envelope["seed"],
        candidate_sha256=_sha(envelope["candidate"]),
        prompt_hash=_sha(envelope["prompt_hash"]),
        checker_module="harness.matmul_oracle",
        checker_source_sha256=_sha("harness.matmul_oracle@" + version),
        executes_candidate_code=False,
        oracle_qa_card_hash=envelope["oracle_output_hash"],
        held_out_agreement="NOT_RUN",
        evidence_kind=EvidenceKind.CONSTRUCTIVE,
        tier=Tier.CONSTRUCTION_CERTIFICATE,
        verdict=Verdict(envelope["verdict"]), attribution=Attribution.CANDIDATE,
        objective="7", incumbent_objective="7", incumbent_source="strassen_1969",
        coverage={"predicate_exact": True, "search_space_enumerated": False,
                  "enumerated_fraction": "0", "stop_reason": "complete",
                  "guarantee_weakens_above": None},
        raw_stdout_sha256=hashlib.sha256(
            envelope["oracle_stdout_excerpt"].encode("utf-8")).hexdigest(),
        analysis_script_sha256=_sha("make_receipt.py"),
        denominator=Denominator(
            attempts=4, group_size=4, oracle_calls_consumed=5, hits=1, undecided=0,
            unverifiable=0, parse_failures=0, timeouts=0, tokens_in=0, tokens_out=0,
            cache_hit_tokens=0, tasks_proposed=1, tasks_filtered_out=0,
            filter_id="none", filter_hash=_sha("none"), retries=0,
            oracle_feedback_visible=False, filter_is_learned=False),
        budget=Budget(600, 4096, 5, exhausted=False),
        model_ref=envelope["model_ref"], base_weights_digest="",
        harness_version=version,
    )


def main(argv) -> int:
    out = Path(argv[1])
    envelope = json.loads((out / "gate_envelope.json").read_text(encoding="utf-8"))
    version = metadata.version("flywheel-verify")
    values = _values(envelope, version)
    required = [f.name for f in dataclasses.fields(Receipt)
                if f.default is dataclasses.MISSING
                and f.default_factory is dataclasses.MISSING]
    missing = sorted(set(required) - set(values))
    if missing:
        print("this release's Receipt needs fields the table lacks: "
              + ", ".join(missing), file=sys.stderr)
        return 1
    known = {f.name for f in dataclasses.fields(Receipt)}
    receipt = Receipt(**{k: v for k, v in values.items() if k in known})
    body = receipt.to_dict()
    if Receipt.from_dict(body).claim_sha256() != receipt.claim_sha256():
        print("the release cannot read back its own receipt", file=sys.stderr)
        return 1
    (out / "receipt.json").write_bytes(
        (json.dumps(body, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(f"flywheel-verify {version}: {body['schema']} {receipt.claim_sha256()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
