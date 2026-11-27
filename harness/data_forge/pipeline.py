"""End-to-end 6-stage Data Forge pipeline runner and CLI."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from .adapters import run_domain_adapter, stage1_provenance_firewall
from .common import extract_code_snippet, extract_row_text, word_tokens
from .dedup_and_holdout import HoldoutDecontaminator, ThreeTierDeduplicator
from .oracles import (
    synthesize_oracle_verified_rows,
    synthesize_search_from_the_start_rows,
    validate_oracle_candidate,
)
from .scoring_and_seal import (
    build_merkle_and_seal,
    score_entropy_and_difficulty,
    verify_sealed_dataset,
)
from .traps import run_post_seal_merkle_tamper_trap, run_pre_seal_traps


def iter_raw_jsonl(
    path: Path,
    source_label: str,
    limit: int | None = None,
) -> Iterable[tuple[int, dict[str, Any] | None, str | None]]:
    """Stream JSONL or JSONL.GZ records while isolating malformed UTF-8 and JSON rows."""
    opener = gzip.open if path.suffix == ".gz" else open
    yielded = 0
    with opener(path, "rb") as fh:
        for line_no, raw in enumerate(fh, start=1):
            if limit is not None and yielded >= limit:
                break
            if not raw.strip():
                continue
            yielded += 1
            try:
                obj = json.loads(raw.decode("utf-8"))
                if not isinstance(obj, dict):
                    yield line_no, None, "MALFORMED_INPUT:NON_OBJECT_JSON"
                    continue
                obj["_source_corpus"] = source_label
                yield line_no, obj, None
            except UnicodeDecodeError:
                yield line_no, None, "MALFORMED_INPUT:INVALID_UTF8"
            except json.JSONDecodeError:
                yield line_no, None, "MALFORMED_INPUT:INVALID_JSON"


def run_data_forge(
    input_specs: Sequence[tuple[Path, str, int | None]],
    holdout_path: Path | None,
    out_dir: Path,
    *,
    run_oracle_synthesis: bool = True,
    inject_planted_traps: bool = False,
    formulas_tsv_path: Path | None = None,
    include_buildlang: bool | None = None,
    buildc_runner: Callable[[str], bool] | None = None,
    max_domain_share: float = 0.85,
) -> dict[str, Any]:
    """Execute the 6-stage fail-closed Data Forge pipeline and return its dataset card."""
    t0 = time.perf_counter()
    holdout_rows: list[dict[str, Any]] = []
    if holdout_path and holdout_path.is_file():
        for _, obj, err in iter_raw_jsonl(holdout_path, "sealed_holdout"):
            if obj is not None and err is None:
                holdout_rows.append(obj)

    decontam = HoldoutDecontaminator(holdout_rows)
    dedup = ThreeTierDeduplicator(max_hamming=3)
    surviving: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    input_total = 0
    planted_trap_results: dict[str, str] = {}

    def record_reject(row_idx: int, src: str, stage: str, reason: str, trap_id: str | None = None) -> None:
        reason_counts[reason] += 1
        rejected.append({
            "input_index": row_idx, "source_corpus": src, "stage": stage,
            "reason": reason, "trap_id": trap_id,
        })
        if trap_id:
            planted_trap_results[trap_id] = f"CAUGHT:{stage}:{reason}"

    def process_row(row_idx: int, row: dict[str, Any], oracle_verified: bool = False) -> None:
        src = str(row.get("_source_corpus", "unknown"))
        trap_id = row.get("_planted_trap_id")
        text = extract_row_text(row)

        ok1, r1, prov = stage1_provenance_firewall(row, text)
        if not ok1:
            record_reject(row_idx, src, "stage1_firewall", r1, trap_id)
            return
        ok_dom, r_dom, dom_meta = run_domain_adapter(row, text)
        if not ok_dom:
            record_reject(row_idx, src, "stage1_domain_adapter", r_dom, trap_id)
            return
        if dom_meta:
            prov["domain_adapter"] = dom_meta

        tokens = word_tokens(text)
        code = extract_code_snippet(row, text)
        ok2, r2 = dedup.check_and_add(text, tokens, code)
        if not ok2:
            record_reject(row_idx, src, "stage2_dedup", r2, trap_id)
            return
        ok3, r3 = decontam.is_clean(tokens, code)
        if not ok3:
            record_reject(row_idx, src, "stage3_decontam", r3, trap_id)
            return
        if row.get("oracle_kind"):
            ok4, r4 = validate_oracle_candidate(row, buildc_runner=buildc_runner)
            if not ok4:
                record_reject(row_idx, src, "stage4_oracle_sanitizer", r4, trap_id)
                return
            oracle_verified = True

        metrics = score_entropy_and_difficulty(text, tokens, oracle_verified)
        domain = str(row.get("domain") or row.get("task") or row.get("category") or "general")
        tier_counts[metrics["difficulty_tier"]] += 1
        domain_counts[domain] += 1
        forge_id = f"df-{len(surviving):07d}"
        surviving.append({
            "forge_id": forge_id,
            "orig_id": str(row.get("id", row.get("row_id", forge_id))),
            "domain": domain,
            "oracle_verified": oracle_verified,
            "provenance": prov,
            "metrics": metrics,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text": text,
        })

    first_surviving_text: str | None = None
    for path, label, limit in input_specs:
        for _, obj, err in iter_raw_jsonl(path, label, limit=limit):
            input_total += 1
            if err is not None or obj is None:
                record_reject(input_total, label, "stage0_parse", err or "MALFORMED_INPUT")
                continue
            process_row(input_total, obj)
            if first_surviving_text is None and surviving:
                first_surviving_text = surviving[0]["text"]

    synth_added = 0
    sfts_added = 0
    if run_oracle_synthesis:
        for s_row in synthesize_oracle_verified_rows(count_f64=12, include_buildlang=include_buildlang):
            input_total += 1
            before = len(surviving)
            process_row(input_total, s_row)
            if len(surviving) > before:
                synth_added += 1
        for sf_row in synthesize_search_from_the_start_rows(formulas_tsv_path=formulas_tsv_path, limit=24):
            input_total += 1
            before = len(surviving)
            process_row(input_total, sf_row)
            if len(surviving) > before:
                synth_added += 1
                sfts_added += 1

    if inject_planted_traps:
        input_total = run_pre_seal_traps(input_total, first_surviving_text, holdout_rows, process_row, record_reject)

    elapsed_s = max(1e-6, time.perf_counter() - t0)
    stats = {
        "input_rows_total": input_total,
        "surviving_rows": len(surviving),
        "rejected_rows": len(rejected),
        "retention_ratio": round(len(surviving) / max(1, input_total), 4),
        "dedup_and_filter_drop_ratio": round(len(rejected) / max(1, input_total), 4),
        "oracle_synthesized_verified_rows": synth_added,
        "sfts_retrieval_trace_rows": sfts_added,
        "holdout_items_indexed": decontam.holdout_count,
        "elapsed_seconds": round(elapsed_s, 4),
        "throughput_rows_per_sec": round(input_total / elapsed_s, 1),
        "rejection_reasons": dict(reason_counts),
        "dedup_breakdown": dict(dedup.stats),
        "difficulty_tiers": dict(tier_counts),
        "top_domains": dict(domain_counts.most_common(12)),
        "max_domain_share_limit": max_domain_share,
        "planted_traps": planted_trap_results,
    }
    card = build_merkle_and_seal(surviving, rejected, out_dir, stats)
    clean_ok, clean_verdict = verify_sealed_dataset(out_dir / "forged_dataset.jsonl.gz", out_dir / "merkle_proof_bundle.json")
    if not (clean_ok and clean_verdict == "MATCH"):
        raise RuntimeError(f"clean seal verification failed: {clean_verdict}")

    if inject_planted_traps and surviving:
        planted_trap_results["trap6_post_seal_merkle_tamper"] = run_post_seal_merkle_tamper_trap(out_dir)
        card["stats"]["planted_traps"] = planted_trap_results
        card["stats"]["planted_traps_caught"] = f"{len(planted_trap_results)}/9"
        (out_dir / "dataset_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return card


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for Proof-Carrying Data Forge."""
    ap = argparse.ArgumentParser(description="Proof-Carrying Data Forge 6-stage pipeline.")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--holdout", type=Path, default=None)
    ap.add_argument("--formulas-tsv", type=Path, default=None)
    ap.add_argument("--input", action="append", default=[], help="path[::label[::limit]]")
    ap.add_argument("--inject-traps", action="store_true")
    ap.add_argument("--no-synth", action="store_true")
    args = ap.parse_args(argv)

    specs: list[tuple[Path, str, int | None]] = []
    for raw in args.input:
        parts = raw.split("::")
        p = Path(parts[0])
        lbl = parts[1] if len(parts) > 1 and parts[1] else p.stem
        lim = int(parts[2]) if len(parts) > 2 and parts[2] else None
        specs.append((p, lbl, lim))

    card = run_data_forge(
        specs, args.holdout, args.out_dir,
        run_oracle_synthesis=not args.no_synth,
        inject_planted_traps=args.inject_traps,
        formulas_tsv_path=args.formulas_tsv,
    )
    print(json.dumps(card, indent=2, sort_keys=True))
    return 0
