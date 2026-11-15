#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
emet.reporters.deepeval - EMET DeepEval reporter: mint an emet-verifiable receipt
over a completed DeepEval evaluation.

Optional, out-of-core, stdlib-only reporter. It ships in the wheel as the
`emet.reporters` subpackage but is NOT part of the minimal Trusted Computing Base:
the minimal-TCB guarantee (SPEC section 10), the zero-dependency posture, and the
selftest artifact-of-record (SPEC s.14) all apply to the emet/ named core ONLY
(membrane, organs, monitor, corpus, verdict, report), never to this reporter. Like
the emet adapters it EMITS DATA: it never signs on the operator's behalf, enforces,
uploads, or actuates.

Given a completed DeepEval evaluation, it gathers a STABLE eval record - model
identifier, dataset digest (a hash of the test-case inputs, never the raw cases),
metric/judge name + version, per-case pass/score as STRINGS, and config -
canonicalizes it (SPEC s.7 byte form), and mints a portable emet witness receipt
(SPEC s.17) that BINDS that record by content address. `emet check <receipt.json>`
re-verifies it offline with zero shared state; corrupting one byte of the sealed
record re-hashes to a different id and flips the verdict away from RECEIPT_VALID.

What the receipt DOES and does NOT assert:
  * It binds the PROVENANCE and INTEGRITY of the eval record: which model was run,
    over which dataset (by digest + count), under which metric/judge, and which
    scores the metrics reported. Re-derivation is a FACT, not a trust decision -
    the receipt-level verdict stays inside the closed RECEIPT lattice
    (RECEIPT_VALID / RECEIPT_TAMPERED / RECEIPT_UNVERIFIABLE, verdict.py) and maps
    to no authority word.
  * It makes NO claim about model quality beyond the numbers the metrics already
    reported. Per-case pass/score are copied verbatim (as strings) into the sealed
    record; emet does not adjudicate them. The emet verdict_record is left EMPTY on
    purpose: a MATCH/DRIFT there would be a BYTE-INTEGRITY claim, not an eval
    outcome, and conflating the two would misuse the lattice.

Determinism + honesty:
  * The sealed record contains NO floats (scores/thresholds are strings), so its
    canonical bytes are stable across platforms.
  * The dataset is stored as a sha256 digest + a count, NEVER the raw test cases,
    so a receipt can travel without leaking the eval inputs.

DeepEval is an OPTIONAL, LAZY import: building a record and minting a receipt from
an already-completed evaluation object need NO deepeval install (the object is read
structurally). Only the convenience that RUNS an evaluation (evaluate_and_mint)
imports deepeval, and it raises a clear error if it is absent.

Usage:
    pip install emet            # the zero-dep core; provides `emet check`
    pip install emet[deepeval]  # or:  pip install deepeval

    from emet.reporters.deepeval import mint_receipt
    # `result` is whatever deepeval.evaluate(...) returned.
    receipt, record_path, receipt_path = mint_receipt(
        result, model="gpt-4o-2024-08-06",
        config={"temperature": "0", "run": "nightly"},
        out_dir="eval-out",
    )
    # writes eval-out/emet-eval-record.json  (the sealed record, canonical bytes)
    #    and eval-out/emet-eval-receipt.json (the portable receipt)
    # re-verify offline, zero shared state:
    #      emet check eval-out/emet-eval-receipt.json                 -> RECEIPT_VALID
    #      emet check eval-out/emet-eval-receipt.json --recompute-from-paths
    # Any single-byte change to the sealed record flips RECEIPT_VALID away.

    # To run the evaluation AND mint in one step (needs deepeval installed):
    from emet.reporters.deepeval import evaluate_and_mint
    receipt, record_path, receipt_path = evaluate_and_mint(
        test_cases, metrics, model="gpt-4o-2024-08-06", out_dir="eval-out")
"""
import hashlib
import os
import sys

# In-package imports: the reporter ships inside the emet wheel, so the named core
# is importable with no sys.path manipulation. These are core modules (report is
# the canonical-bytes renderer, witness_receipt the portable-receipt path); the
# reporter adds NO dependency to them and the core never imports back the other way.
from emet import report, witness_receipt

EVAL_RECORD_SCHEMA = "emet-eval-record/v1"
RECORD_FILENAME = "emet-eval-record.json"
RECEIPT_FILENAME = "emet-eval-receipt.json"


def _sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def _as_str(value):
    # No floats reach the sealed record: every scalar is stringified. None becomes
    # the empty string so a missing field is stable, never a null that shifts bytes.
    return "" if value is None else str(value)


def _bool_str(value):
    # Per-case pass is a string. A genuine unknown is recorded as "unknown" rather
    # than guessed, so the record never overclaims what the harness reported.
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    return _as_str(value)


def _string_map(mapping):
    # config is coerced to a string->string map so it carries no float and its
    # canonical bytes are stable.
    if not mapping:
        return {}
    return {_as_str(k): _as_str(v) for k, v in mapping.items()}


def _get(obj, *names, default=None):
    # Read a field from a deepeval-shaped object OR a plain dict, tolerating the
    # attribute-name drift across deepeval versions (e.g. metrics_data / metrics).
    for name in names:
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
        elif hasattr(obj, name):
            return getattr(obj, name)
    return default


def _deepeval_version():
    # The harness version stamped into the record. Never raises: absent deepeval
    # records "unknown" so a record built from fake/replayed results stays honest.
    try:
        import deepeval  # noqa: F401  (optional, lazy)
        return _as_str(getattr(deepeval, "__version__", "unknown")) or "unknown"
    except Exception:
        return "unknown"


def _iter_test_results(evaluation):
    # Accept a deepeval EvaluationResult (has .test_results) OR a bare list/tuple
    # of test-result-shaped objects. Anything else is not a recognized evaluation.
    results = _get(evaluation, "test_results")
    if results is None:
        if isinstance(evaluation, (list, tuple)):
            results = list(evaluation)
        else:
            raise ValueError(
                "not a recognized DeepEval evaluation: expected an object with "
                ".test_results or a list of test results")
    return list(results)


def _case_input(test_result):
    # The dataset digest covers INPUTS only, never actual/expected outputs, so the
    # digest identifies the dataset without binding the model's answers.
    return _as_str(_get(test_result, "input", default=""))


def _metric_record(metric):
    return {
        "judge_model": _as_str(_get(metric, "evaluation_model", "model", default="")),
        "name": _as_str(_get(metric, "name", default="")),
        "passed": _bool_str(_get(metric, "success")),
        "score": _as_str(_get(metric, "score", default="")),
        "threshold": _as_str(_get(metric, "threshold", default="")),
    }


def _case_record(index, test_result):
    metrics = _get(test_result, "metrics_data", "metrics", default=[]) or []
    return {
        "index": str(index),
        "metrics": [_metric_record(m) for m in metrics],
        "passed": _bool_str(_get(test_result, "success")),
    }


def build_eval_record(evaluation, *, model, config=None, dataset_inputs=None,
                      harness_version=None):
    """Gather a stable, canonical eval record from a completed DeepEval evaluation.

    Pure and deepeval-free: reads the evaluation structurally, so it works on a
    real EvaluationResult, a list of TestResult objects, or fakes of the same
    shape. `model` is the model identifier (required). `config` is coerced to a
    string map. `dataset_inputs`, if given, overrides the inputs hashed for the
    dataset digest (else the per-case .input values are used). No float enters the
    record; scores/thresholds/pass are strings.
    """
    if not isinstance(model, str) or not model:
        raise ValueError("model must be a non-empty identifier string")
    results = _iter_test_results(evaluation)
    inputs = list(dataset_inputs) if dataset_inputs is not None \
        else [_case_input(r) for r in results]
    dataset_digest = _sha256_hex(report.canonical(inputs).encode("utf-8"))
    cases = [_case_record(i, r) for i, r in enumerate(results)]
    names = sorted({m["name"] for c in cases for m in c["metrics"] if m["name"]})
    judges = sorted({m["judge_model"] for c in cases for m in c["metrics"]
                     if m["judge_model"]})
    return {
        "schema": EVAL_RECORD_SCHEMA,
        "model": model,
        "dataset": {
            "algorithm": "sha256",
            "count": len(results),
            "covers": "test_case_inputs",
            "digest": dataset_digest,
        },
        "metric": {
            "harness": "deepeval",
            "harness_version": harness_version if harness_version is not None
            else _deepeval_version(),
            "judge_models": judges,
            "names": names,
        },
        "config": _string_map(config),
        "cases": cases,
    }


def mint_receipt(evaluation, *, model, config=None, dataset_inputs=None,
                 out_dir=None, now=None, signing_key=None, harness_version=None,
                 record_filename=RECORD_FILENAME, receipt_filename=RECEIPT_FILENAME):
    """Build the eval record, seal it, and mint an emet witness receipt over it.

    Writes the canonical record bytes to out_dir/record_filename and the receipt to
    out_dir/receipt_filename (both byte-stable via report.canonical), then returns
    (receipt_dict, record_path, receipt_path). The receipt binds the record's
    content address through the anchor path: anchor emits NO verdict, so the
    receipt's verdict_record is empty BY DESIGN - emet witnesses the record's
    integrity, it does not adjudicate the eval. `now` (ISO-8601 Z) pins the one
    wall-clock field for deterministic fixtures; `signing_key` (bytes) optionally
    adds the out-of-spec HMAC (SPEC s.17.4).
    """
    record = build_eval_record(evaluation, model=model, config=config,
                               dataset_inputs=dataset_inputs,
                               harness_version=harness_version)
    out_dir = out_dir or os.getcwd()
    os.makedirs(out_dir, exist_ok=True)
    canonical_bytes = report.canonical(record).encode("utf-8")
    record_path = os.path.join(out_dir, record_filename)
    with open(record_path, "wb") as handle:
        handle.write(canonical_bytes)
    digest = _sha256_hex(canonical_bytes)
    # An anchor-style command envelope: subject = the sealed record, no verdict.
    env = {"command": "anchor",
           "results": [{"path": record_filename, "sha256": digest}]}
    receipt = witness_receipt.emit_receipt(
        env, base_dir=out_dir, now=now, signing_key=signing_key)
    receipt_path = os.path.join(out_dir, receipt_filename)
    with open(receipt_path, "w", encoding="utf-8") as handle:
        handle.write(report.canonical(receipt))
    return receipt, record_path, receipt_path


def require_deepeval():
    """Lazily import deepeval, or raise a clear, actionable error if it is absent.

    Used only by the eval-RUNNING convenience. Minting a receipt from an
    already-completed evaluation (build_eval_record / mint_receipt) needs no
    deepeval, so the import stays off the record-building path.
    """
    try:
        import deepeval
        return deepeval
    except ImportError as exc:
        raise RuntimeError(
            "deepeval is not installed. evaluate_and_mint runs the evaluation and "
            "so requires it; install with `pip install deepeval` or "
            "`pip install emet[deepeval]`. (mint_receipt on an already-completed "
            "evaluation needs no deepeval.)"
        ) from exc


def evaluate_and_mint(test_cases, metrics, *, model, config=None, out_dir=None,
                      now=None, signing_key=None, **evaluate_kwargs):
    """Run deepeval.evaluate(test_cases, metrics, ...) then mint a receipt over it.

    Requires deepeval (raises a clear error via require_deepeval() if absent).
    Returns (receipt_dict, record_path, receipt_path) exactly like mint_receipt.
    """
    deepeval = require_deepeval()
    result = deepeval.evaluate(test_cases, metrics, **evaluate_kwargs)
    return mint_receipt(result, model=model, config=config, out_dir=out_dir,
                        now=now, signing_key=signing_key)


def main(argv=None):
    # This adapter's surface is the Python API above (a DeepEval evaluation object
    # is not a CLI argument). Verification is emet's job: `emet check <receipt>`.
    sys.stderr.write(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
