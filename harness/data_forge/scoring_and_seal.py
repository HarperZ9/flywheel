"""Stage 5 dual-lens salience scoring and Stage 6 RFC 6962 Merkle sealing."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import zlib
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness.merkle import inclusion_proof, merkle_root, verify_inclusion

from .common import FLYWHEEL_MODULES_LINKED, SCHEMA_CARD, SCHEMA_MERKLE, SLOP_MARKERS, canonical_json_bytes


def score_subjective_slop_density(text: str, token_count: int) -> tuple[int, float]:
    """Articulate-aligned structural slop detector rejecting homogenized LLM boilerplate."""
    hits = sum(len(pat.findall(text)) for pat in SLOP_MARKERS)
    em_dashes = text.count("\u2014")
    if em_dashes >= 3:
        hits += em_dashes - 2
    density = hits / max(1.0, token_count / 100.0)
    return hits, round(density, 4)


def score_entropy_and_difficulty(
    text: str,
    tokens: Sequence[str],
    oracle_verified: bool,
    epistemic_band: str = "empirical_verified",
) -> dict[str, Any]:
    """Compute dual-lens Shannon entropy, compressibility, Articulate slop penalty, and tier."""
    n = len(tokens)
    if n == 0:
        shannon = 0.0
        uniq_ratio = 0.0
    else:
        counts = Counter(tokens)
        shannon = -sum((c / n) * math.log2(c / n) for c in counts.values())
        uniq_ratio = len(counts) / n
    raw_bytes = text.encode("utf-8", errors="ignore")
    comp_ratio = len(zlib.compress(raw_bytes, level=6)) / max(1, len(raw_bytes))
    slop_hits, slop_density = score_subjective_slop_density(text, n)
    slop_penalty = min(0.35, slop_density * 0.12)

    salience = round(
        max(
            0.0,
            min(
                1.0,
                (shannon / 8.0) * 0.50
                + min(comp_ratio, 1.0) * 0.25
                + uniq_ratio * 0.10
                + (0.15 if oracle_verified else 0.0)
                - slop_penalty,
            ),
        ),
        4,
    )
    if oracle_verified or (shannon >= 5.4 and n >= 80 and slop_hits == 0):
        tier = "tier_3_frontier"
    elif shannon >= 4.0 and n >= 25:
        tier = "tier_2_applied"
    else:
        tier = "tier_1_foundation"

    top_terms = [w for w, _ in Counter(w for w in tokens if len(w) >= 4).most_common(6)]
    return {
        "token_count": n,
        "shannon_entropy_bits": round(shannon, 4),
        "unique_token_ratio": round(uniq_ratio, 4),
        "zlib_compression_ratio": round(comp_ratio, 4),
        "articulate_slop_hits": slop_hits,
        "articulate_slop_density": slop_density,
        "salience_score": salience,
        "difficulty_tier": tier,
        "epistemic_band": epistemic_band,
        "cleanroom_property_signature": " ".join(top_terms[:6]),
    }


def _try_write_parquet(surviving_rows: list[dict[str, Any]], parquet_path: Path) -> bool:
    """Optionally emit a zstd-compressed Parquet table when pyarrow is installed."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return False

    pq_rows = [
        {
            "forge_id": r["forge_id"],
            "domain": r["domain"],
            "spdx_license": r["provenance"]["spdx_license"],
            "source_corpus": r["provenance"]["source_corpus"],
            "difficulty_tier": r["metrics"]["difficulty_tier"],
            "shannon_entropy_bits": float(r["metrics"]["shannon_entropy_bits"]),
            "salience_score": float(r["metrics"]["salience_score"]),
            "oracle_verified": bool(r["oracle_verified"]),
            "text_sha256": r["text_sha256"],
            "text": r["text"],
        }
        for r in surviving_rows
    ]
    if not pq_rows:
        return False
    table = pa.Table.from_pylist(pq_rows)
    pq.write_table(table, parquet_path, compression="zstd")
    return True


def build_merkle_and_seal(
    surviving_rows: list[dict[str, Any]],
    rejected_rows: list[dict[str, Any]],
    out_dir: Path,
    stats: dict[str, Any],
) -> dict[str, Any]:
    """Write JSONL.GZ, optional Parquet, rejected audit log, RFC 6962 bundle, and dataset card."""
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "forged_dataset.jsonl.gz"
    rejected_path = out_dir / "rejected_audit_log.jsonl.gz"
    merkle_path = out_dir / "merkle_proof_bundle.json"
    card_path = out_dir / "dataset_card.json"
    parquet_path = out_dir / "forged_dataset.parquet"

    leaf_bytes: list[bytes] = []
    with gzip.open(jsonl_path, "wb") as gz:
        for row in surviving_rows:
            line = canonical_json_bytes(row)
            leaf_bytes.append(line)
            gz.write(line + b"\n")

    with gzip.open(rejected_path, "wb") as gz:
        for rej in rejected_rows:
            gz.write(canonical_json_bytes(rej) + b"\n")

    root = merkle_root(leaf_bytes)
    root_hex = "sha256:" + root.hex()

    sample_indices = sorted({0, len(leaf_bytes) // 2, len(leaf_bytes) - 1}) if leaf_bytes else []
    sample_proofs = []
    for idx in sample_indices:
        pf = inclusion_proof(leaf_bytes, idx)
        if not verify_inclusion(leaf_bytes[idx], idx, len(leaf_bytes), pf, root):
            raise RuntimeError(f"Merkle inclusion self-check failed at index {idx}")
        sample_proofs.append({
            "index": idx,
            "row_id": surviving_rows[idx]["forge_id"],
            "leaf_sha256": hashlib.sha256(b"\x00" + leaf_bytes[idx]).hexdigest(),
            "proof_hex": [p.hex() for p in pf],
        })

    parquet_emitted = _try_write_parquet(surviving_rows, parquet_path)

    merkle_bundle = {
        "schema": SCHEMA_MERKLE,
        "rfc": "RFC-6962",
        "flywheel_merkle_linked": FLYWHEEL_MODULES_LINKED,
        "leaf_count": len(leaf_bytes),
        "merkle_root": root_hex,
        "sample_inclusion_proofs": sample_proofs,
        "dataset_jsonl_gz_sha256": "sha256:" + hashlib.sha256(jsonl_path.read_bytes()).hexdigest(),
    }
    merkle_path.write_text(json.dumps(merkle_bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    card = {
        "schema": SCHEMA_CARD,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "flywheel_modules_linked": FLYWHEEL_MODULES_LINKED,
        "merkle_root": root_hex,
        "parquet_emitted": parquet_emitted,
        "outputs": {
            "jsonl_gz": str(jsonl_path),
            "parquet": str(parquet_path) if parquet_emitted else None,
            "rejected_audit_log": str(rejected_path),
            "merkle_proof_bundle": str(merkle_path),
        },
        "stats": stats,
    }
    card_path.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return card


def verify_sealed_dataset(jsonl_gz_path: Path, merkle_bundle_path: Path) -> tuple[bool, str]:
    """Fail-closed verifier recomputing RFC 6962 Merkle root and sample inclusion proofs."""
    bundle = json.loads(merkle_bundle_path.read_text(encoding="utf-8"))
    expected_root_hex = bundle["merkle_root"]
    expected_root = bytes.fromhex(expected_root_hex.removeprefix("sha256:"))

    leaves: list[bytes] = []
    with gzip.open(jsonl_gz_path, "rb") as gz:
        for raw_line in gz:
            line = raw_line.rstrip(b"\r\n")
            if line:
                leaves.append(line)

    if len(leaves) != bundle["leaf_count"]:
        return False, f"LEAF_COUNT_MISMATCH:{len(leaves)}!={bundle['leaf_count']}"

    actual_root = merkle_root(leaves)
    if actual_root != expected_root:
        return False, "MERKLE_TAMPER_DETECTED:ROOT_MISMATCH"

    for sample in bundle.get("sample_inclusion_proofs", []):
        idx = int(sample["index"])
        pf = [bytes.fromhex(h) for h in sample["proof_hex"]]
        if not verify_inclusion(leaves[idx], idx, len(leaves), pf, expected_root):
            return False, f"MERKLE_TAMPER_DETECTED:PROOF_FAILED:{idx}"

    return True, "MATCH"
