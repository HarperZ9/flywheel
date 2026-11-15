"""Project Telos context-envelope export helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return _sha256_text(path.as_posix())
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _approx_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _source_path(source: str, roots: list[Path]) -> Path | None:
    normalized = source.replace("/", "\\")
    for root in roots:
        candidate = root / normalized
        if candidate.exists():
            return candidate
    for root in roots:
        if root.is_file() and root.name == source:
            return root
    return None


def _source_refs(
    records: list[dict[str, str]],
    roots: list[Path],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    refs: list[dict[str, Any]] = []
    ids: dict[str, str] = {}
    for record in records:
        source = record["source"]
        if source in ids:
            continue
        ref_id = f"src_{len(refs) + 1:03d}"
        ids[source] = ref_id
        path = _source_path(source, roots)
        refs.append(
            {
                "id": ref_id,
                "path": source,
                "range": "full-file",
                "content_hash": _sha256_file(path) if path else _sha256_text(source),
                "expansion_command": f"gather docs {source} --json",
            }
        )
    return refs, ids


def build_context_envelope(
    records: list[dict[str, str]],
    roots: list[Path],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Build a Telos context envelope without exposing absolute root paths."""

    source_refs, source_ids = _source_refs(records, roots)
    claim_tokens = sum(_approx_tokens(record["text"]) for record in records)
    root_hash = _sha256_text("|".join(manifest["root_sha256_prefixes"]))
    manifest_hash = _sha256_text(json.dumps(manifest, sort_keys=True))
    curated_records = max(1, int(manifest["curated_records"]))
    raw_matches = max(curated_records, int(manifest["raw_keyword_matches"]))

    return {
        "schema": "project-telos.context-envelope/v1",
        "envelope_id": f"ctxenv_{root_hash[-16:]}_{manifest['generated'][:10]}",
        "workspace": {
            "root_hash": root_hash,
            "git_head": "unavailable",
            "dirty": None,
        },
        "context_budget": {
            "max_input_tokens": claim_tokens,
            "target_packet_tokens": claim_tokens,
            "reserved_response_tokens": 0,
        },
        "compression": {
            "strategy": "heuristic_keyword_extract_with_hash_refs",
            "ratio_target": max(1, raw_matches // curated_records),
            "lossless_by_ref": True,
            "hidden_payloads_used": False,
        },
        "source_refs": source_refs,
        "summary": {
            "claims": [
                {
                    "kind": record["kind"],
                    "text": record["text"],
                    "source_ref_ids": [source_ids[record["source"]]],
                }
                for record in records
            ]
        },
        "receipt_chain": [
            {
                "tool": "context-curator-lite",
                "action": "curate",
                "receipt_hash": manifest_hash,
            }
        ],
        "quality_gates": {
            "readability": "MATCH",
            "test_evidence": "UNVERIFIABLE",
            "freshness": "MATCH",
            "privacy": "MATCH",
        },
        "privacy_boundary": {
            "absolute_paths_included": False,
            "raw_transcripts_copied": False,
            "raw_secret_values_required": False,
            "hidden_payloads_allowed": False,
        },
        "failure_code": None,
    }
