"""Run the local large-model comparators on explicit diagnostic examples."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from harness.classifier_dataset import load_examples_jsonl
from harness.evidence_json import canonical_sha256


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 8:
        raise ValueError("batch size must be 1..8")
    rows = load_examples_jsonl(args.data)
    if not 1 <= len(rows) <= 256:
        raise ValueError("experiment requires 1..256 explicit examples")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    import torch
    from .classifier_token_runtime import load_local_comparator
    from .classifier_token_generation import TransformersJSONGenerationComparator

    torch.manual_seed(1729)
    started = perf_counter()
    comparator = load_local_comparator(args.model, load_in_4bit=True,
        dtype=torch.bfloat16, device_map="cuda", max_input_tokens=2048)
    torch.cuda.synchronize()
    load_ms = (perf_counter()-started)*1000
    generator = TransformersJSONGenerationComparator(comparator.model, comparator.tokenizer,
        max_input_tokens=2048, max_new_tokens=96)
    modes, timing = {}, []
    for mode in ("first_token", "json_generation"):
        result_rows = []
        for offset in range(0, len(rows), args.batch_size):
            chunk = rows[offset:offset+args.batch_size]
            requests = [row["request"] for row in chunk]
            torch.cuda.synchronize()
            started = perf_counter()
            outputs = (comparator.score_requests(requests) if mode == "first_token"
                       else generator.generate_requests(requests))
            torch.cuda.synchronize()
            elapsed = (perf_counter()-started)*1000
            if len(outputs) != len(chunk):
                raise ValueError("comparator response count mismatch")
            timing.append({"mode": mode, "offset": offset, "requests": len(chunk),
                           "batch_wall_ms": elapsed})
            for row, output in zip(chunk, outputs):
                result = output["contract_result"]
                if result["request_sha256"] != row["request_sha256"]:
                    raise ValueError("response request hash mismatch")
                targets = row["acceptable_choice_ids"]
                correct = (result["choice_id"] in targets if targets else
                           result["reason_code"] == "abstain")
                result_rows.append({"task_family": row["task_family"],
                    "case_id": row["request"]["decision_ref"], "correct": correct,
                    "target_choice_ids": targets, "output": output})
            print(json.dumps({"mode": mode, "completed": offset+len(chunk),
                              "batch_ms": round(elapsed, 1)}), flush=True)
        modes[mode] = result_rows
        (out/f"{mode}-predictions.json").write_text(json.dumps(result_rows, indent=2,
            allow_nan=False), encoding="utf8")
    report = {"schema": "flywheel.classifier-token-experiment/v1",
        "model_directory": args.model, "weights_freshly_hashed": False,
        "quantization": "NF4 double quantization, bfloat16 compute",
        "seed": 1729, "batch_size": args.batch_size, "examples": len(rows),
        "data_sha256": canonical_sha256(rows), "model_load_ms": load_ms,
        "max_memory_allocated_bytes": torch.cuda.max_memory_allocated(),
        "timing": timing, "modes": {},
        "does_not_prove": ["Synthetic labels are not independent human ground truth.",
            "No shared-prefix KV cache is implemented in the first-token comparator.",
            "JSON generation uses greedy unconstrained decoding; this is not a grammar-constrained baseline.",
            "Shared desktop GPU batch timings are not isolated full-workflow latency or energy measurements."]}
    for mode, results in modes.items():
        report["modes"][mode] = {family: {
            "correct": sum(r["correct"] for r in results if r["task_family"] == family),
            "total": sum(r["task_family"] == family for r in results)}
            for family in sorted({r["task_family"] for r in results})}
    (out/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf8")
    print(json.dumps(report["modes"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
