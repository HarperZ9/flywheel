"""Offline equal-request classifier comparison; writes private experimental artifacts."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from time import perf_counter

from harness.classifier_dataset import build_split_manifest, load_examples_jsonl
from harness.classifier_metrics import evaluate_probability_cases
from harness.classifier_training import EXAMPLE_KEYS
from harness.evidence_json import canonical_sha256, strict_load_json


def probabilities_from_envelope(envelope: dict) -> dict:
    rows = envelope["scores"]
    if not rows or len({r["choice_id"] for r in rows}) != len(rows):
        raise ValueError("invalid score rows")
    if "probability_like" in rows[0]:
        probs = {r["choice_id"]: r["probability_like"] for r in rows}
        if any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
               for p in probs.values()):
            raise ValueError("invalid probability")
        total = math.fsum(probs.values())
        if abs(total-1) > 1e-6:
            raise ValueError("invalid probability mass")
        return {key: value/total for key, value in probs.items()}
    eligible = {r["choice_id"]: r["score"] for r in rows if r["eligible"]}
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in eligible.values()):
        raise ValueError("invalid raw score")
    probs = {r["choice_id"]: 0.0 for r in rows}
    probs["__abstain__"] = 0.0 if eligible else 1.0
    if eligible:
        peak = max(eligible.values())
        mass = {key: math.exp(value-peak) for key, value in eligible.items()}
        total = math.fsum(mass.values())
        probs.update({key: value/total for key, value in mass.items()})
    return probs


def _load_json(path: str) -> dict:
    with Path(path).open("rb") as handle:
        return strict_load_json(handle.read(16_777_217), max_bytes=16_777_216)


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = (len(values)-1)*q
    left = int(index)
    return values[left] + (values[min(left+1, len(values)-1)]-values[left])*(index-left)


def _runtime(kind: str, artifact: str, device: str):
    if kind == "baseline":
        from harness.classifier_model import LinearClassifierModel
        from harness.classifier_workflows import BaselineScorer
        model = LinearClassifierModel.load_json(artifact)
        return BaselineScorer(model), model.model_ref()
    from .classifier_encoder_artifact import load_encoder_artifact
    from .classifier_encoder_runtime import EncoderClassifierRuntime
    loaded = load_encoder_artifact(artifact, device=device)
    identity = loaded.report["artifact_identity"]
    return EncoderClassifierRuntime(loaded.model, loaded.tokenizer, identity,
                                    device=device, encode_batch_size=16), identity


def run_benchmark(rows: list[dict], runtime, *, model_ref: str, split: str,
                  batch_size: int = 8, synchronize=lambda: None) -> tuple[dict, list]:
    """Only requests are passed to the scorer; labels stay in this evaluator."""
    if not 1 <= batch_size <= 64:
        raise ValueError("invalid benchmark batch size")
    reports, predictions, timings = {}, [], []
    for family in sorted({row["task_family"] for row in rows}):
        cases, family_times = [], []
        selected = [row for row in rows if row["task_family"] == family]
        for offset in range(0, len(selected), batch_size):
            chunk = selected[offset:offset+batch_size]
            requests = [row["request"] for row in chunk]
            if hasattr(runtime, "clear_cache"):
                runtime.clear_cache()
            synchronize()
            start = perf_counter()
            envelopes = runtime.score_batch(requests, task_family=family)
            synchronize()
            cold_ms = (perf_counter()-start)*1000
            synchronize()
            start = perf_counter()
            runtime.score_batch(requests, task_family=family)
            synchronize()
            repeat_ms = (perf_counter()-start)*1000
            if len(envelopes) != len(chunk):
                raise ValueError("benchmark response count mismatch")
            family_times.append(cold_ms/len(chunk))
            timings.append({"family": family, "requests": len(chunk),
                            "empty_embedding_cache_batch_ms": cold_ms,
                            "identical_repeat_batch_ms": repeat_ms})
            for row, envelope in zip(chunk, envelopes):
                if envelope["request_sha256"] != canonical_sha256(row["request"]):
                    raise ValueError("benchmark response binding mismatch")
                probabilities = probabilities_from_envelope(envelope)
                case = {"case_id": row["request"]["decision_ref"],
                        "choice_ids": [c["id"] for c in row["request"]["choices"]],
                        "target_choice_ids": row["acceptable_choice_ids"],
                        "probabilities": probabilities}
                cases.append(case)
                predictions.append({"task_family": family, "source_group": row["source_group"],
                                    "label_provenance": row["label_provenance"], **case})
        reports[family] = {"quality": evaluate_probability_cases(cases),
                           "amortized_batch_ms_p50": _quantile(family_times, .5),
                           "amortized_batch_ms_p95": _quantile(family_times, .95)}
    report = {"schema": "flywheel.classifier-benchmark/v1", "split": split,
              "model_ref": model_ref, "families": reports, "batch_size": batch_size,
              "counts": {"examples": len(rows), "batches": len(timings)},
              "timings": timings, "energy_joules": None, "cost_usd": None,
              "input_sha256": canonical_sha256(rows),
              "does_not_prove": [
                  "Synthetic labels do not establish real workflow quality or production speedup.",
                  "Identical-repeat latency assumes full embedding cache hits for neural inference.",
                  "Amortized batch latency is not single-request latency or full agent completion time.",
                  "Softmax probabilities are uncalibrated; baseline cannot learn abstention yet."]}
    return report, predictions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--splits", required=True)
    parser.add_argument("--split", choices=["train", "calibration", "test"], default="test")
    parser.add_argument("--kind", choices=["baseline", "encoder"], required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    rows = [{key: row[key] for key in EXAMPLE_KEYS} for row in load_examples_jsonl(args.data)]
    splits = _load_json(args.splits)
    manifest = build_split_manifest(rows, splits)
    selected = [r for r in rows if splits[r["source_group"]] == args.split]
    if not selected:
        raise ValueError("empty evaluation split")
    out = Path(args.out)
    if out.exists():
        raise ValueError("output directory exists")
    start = perf_counter()
    runtime, model_ref = _runtime(args.kind, args.artifact, args.device)
    load_ms = (perf_counter()-start)*1000
    sync = lambda: None
    if args.device.startswith("cuda"):
        import torch
        sync = torch.cuda.synchronize
    report, predictions = run_benchmark(selected, runtime, model_ref=model_ref,
        split=args.split, batch_size=args.batch_size, synchronize=sync)
    report.update({"model_load_ms": load_ms, "kind": args.kind,
                   "device": args.device, "split_manifest_sha256": manifest["manifest_sha256"]})
    out.mkdir(parents=True, exist_ok=False)
    for name, value in [("report.json", report), ("predictions.json", predictions)]:
        (out/name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf8")
    print(json.dumps({"model_ref": model_ref, "examples": len(selected),
                      "per_family_accuracy": {f: r["quality"]["metrics"]["top1_accuracy"]
                                              for f, r in report["families"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
