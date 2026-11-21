"""negative_cache.py -- shared negative cache and clean data distillation.

Captures verified dead ends, null findings, and domain failure modes (biology,
dendrology, physics, rendering, evals) as a hash-chained, offline-recheckable
negative cache. Prevents repeated dead-end runs and exports balanced
positive/negative distillation pairs for training models in spiky domains where
clean ground-truth failure data is scarce.

Zero third-party dependencies (stdlib only).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .evidence_json import canonical_sha256

NEGATIVE_RECORD_SCHEMA = "flywheel.negative-record/v1"
NEGATIVE_CACHE_SCHEMA = "flywheel.negative-cache/v1"
DISTILLATION_SCHEMA = "flywheel.clean-distillation/v1"


@dataclass(frozen=True)
class NegativeRecord:
    record_id: str
    domain: str
    hypothesis: str
    failure_mode: str
    parameters: dict[str, Any]
    measurement_sha256: str
    recheck_command: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": NEGATIVE_RECORD_SCHEMA,
            "record_id": self.record_id,
            "domain": self.domain.strip().lower(),
            "hypothesis": self.hypothesis.strip(),
            "failure_mode": self.failure_mode.strip(),
            "parameters": dict(self.parameters),
            "measurement_sha256": self.measurement_sha256,
            "recheck_command": self.recheck_command.strip(),
        }
        payload["record_sha256"] = canonical_sha256(payload)
        return payload


def _normalize_tokens(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return {tok for tok in cleaned.split() if len(tok) >= 3}


def _param_overlap(a: dict[str, Any], b: dict[str, Any]) -> float:
    if not a or not b:
        return 0.0
    shared_keys = set(a) & set(b)
    if not shared_keys:
        return 0.0
    matches = sum(1 for k in shared_keys if a[k] == b[k])
    return matches / max(len(a), len(b))


def build_negative_cache(records: Iterable[NegativeRecord]) -> dict[str, Any]:
    """Seal an ordered list of verified negative records into a hash-chained cache."""
    entries: list[dict[str, Any]] = []
    prev_hash = "0" * 64
    for rec in records:
        if not rec.record_id or not rec.domain or not rec.hypothesis or not rec.measurement_sha256:
            raise ValueError("negative record requires id, domain, hypothesis, and measurement_sha256")
        row = rec.to_dict()
        row["prev_sha256"] = prev_hash
        row["entry_sha256"] = canonical_sha256(row)
        prev_hash = row["entry_sha256"]
        entries.append(row)
    domains = sorted({e["domain"] for e in entries})
    return {
        "schema": NEGATIVE_CACHE_SCHEMA,
        "count": len(entries),
        "domains": domains,
        "head_sha256": prev_hash,
        "entries": entries,
    }


def verify_negative_cache(cache: dict[str, Any]) -> dict[str, Any]:
    """Re-derive every hash link offline; returns MATCH or DRIFT."""
    if not isinstance(cache, dict) or cache.get("schema") != NEGATIVE_CACHE_SCHEMA:
        return {"verdict": "DRIFT", "reason": "invalid cache schema"}
    prev_hash = "0" * 64
    for i, entry in enumerate(cache.get("entries", [])):
        if entry.get("prev_sha256") != prev_hash:
            return {"verdict": "DRIFT", "reason": f"broken chain at index {i}"}
        check_entry = {k: v for k, v in entry.items() if k != "entry_sha256"}
        expected_entry = canonical_sha256(check_entry)
        if entry.get("entry_sha256") != expected_entry:
            return {"verdict": "DRIFT", "reason": f"tampered entry at index {i}"}
        prev_hash = expected_entry
    if cache.get("head_sha256") != prev_hash:
        return {"verdict": "DRIFT", "reason": "head hash mismatch"}
    return {"verdict": "MATCH", "count": len(cache.get("entries", [])), "head_sha256": prev_hash}


def query_dead_ends(
    cache: dict[str, Any],
    *,
    domain: str,
    hypothesis: str,
    parameters: dict[str, Any] | None = None,
    threshold: float = 0.45,
) -> dict[str, Any]:
    """Check whether a proposed experiment matches a known dead end in the cache."""
    dom = domain.strip().lower()
    q_tokens = _normalize_tokens(hypothesis)
    q_params = parameters or {}
    hits: list[dict[str, Any]] = []
    for entry in cache.get("entries", []):
        if entry.get("domain") != dom:
            continue
        e_tokens = _normalize_tokens(entry.get("hypothesis", ""))
        union = q_tokens | e_tokens
        jaccard = (len(q_tokens & e_tokens) / len(union)) if union else 0.0
        p_score = _param_overlap(q_params, entry.get("parameters", {}))
        score = round(0.65 * jaccard + 0.35 * p_score, 4) if q_params else round(jaccard, 4)
        if score >= threshold:
            hits.append({
                "record_id": entry["record_id"],
                "score": score,
                "failure_mode": entry["failure_mode"],
                "measurement_sha256": entry["measurement_sha256"],
            })
    hits.sort(key=lambda h: (-h["score"], h["record_id"]))
    return {
        "verdict": "HIT" if hits else "NOVEL",
        "domain": dom,
        "hit_count": len(hits),
        "hits": hits,
    }


def export_distillation_corpus(
    *,
    domain: str,
    positives: Sequence[dict[str, Any]],
    negative_cache: dict[str, Any],
    max_negatives: int | None = None,
) -> dict[str, Any]:
    """Build a provenance-verified, balanced positive + negative distillation dataset.

    Every row carries its source measurement_sha256 so models trained in spiky
    domains (biology, dendrology, physical materials, formal verification) learn
    explicit failure boundaries alongside verified positive examples.
    """
    dom = domain.strip().lower()
    neg_rows = [
        {
            "label": "negative",
            "record_id": e["record_id"],
            "domain": dom,
            "prompt": e["hypothesis"],
            "outcome": e["failure_mode"],
            "parameters": dict(e["parameters"]),
            "measurement_sha256": e["measurement_sha256"],
        }
        for e in negative_cache.get("entries", [])
        if e.get("domain") == dom
    ]
    if max_negatives is not None:
        neg_rows = neg_rows[: max(0, int(max_negatives))]

    pos_rows: list[dict[str, Any]] = []
    for p in positives:
        if not p.get("measurement_sha256"):
            raise ValueError("positive distillation row requires measurement_sha256")
        pos_rows.append({
            "label": "positive",
            "record_id": str(p["record_id"]),
            "domain": dom,
            "prompt": str(p["prompt"]).strip(),
            "outcome": str(p["outcome"]).strip(),
            "parameters": dict(p.get("parameters") or {}),
            "measurement_sha256": str(p["measurement_sha256"]),
        })

    rows = pos_rows + neg_rows
    total = len(rows)
    neg_share = round(len(neg_rows) / total, 4) if total else 0.0
    corpus = {
        "schema": DISTILLATION_SCHEMA,
        "domain": dom,
        "positive_count": len(pos_rows),
        "negative_count": len(neg_rows),
        "negative_share": neg_share,
        "rows": rows,
    }
    corpus["corpus_sha256"] = canonical_sha256(corpus)
    return corpus
