"""intake.py — research intake: turn a curated external feed (X reposts, a
gather catalog, a reading list) into flywheel build candidates, with a receipt.

This is the self-synthesis arm the operator asked for: the system ingests the
signal a human already curated (what they chose to repost/save), runs it through
the sly fox, and feeds the actionable threads back into the acceleration loop —
so external research compounds into the build instead of evaporating.

Pipeline (all existing organs, wired end-to-end):
    load_feed  -> scout.rank            (ACTIONABLE / INSPIRATION / NOISE by
                                         falsifiable harness-relevance)
               -> scout.synthesize_feed (the top threads as build candidates)
               -> evolve.meta_cycle     (ranked, falsifier-gated: auto-config /
                                         gated-capability / surface-only)

Every accept in the flywheel ships a receipt; so does every intake. The digest
carries a content hash over the ingested feed, so "what did we learn from this
batch" is re-checkable, not a vibe. No source text is mutated; classification is
deterministic (same feed -> same digest hash -> same verdicts).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import scout
from .evolve import meta_cycle


REQUIRED_KEYS = ("id", "text")


@dataclass
class IntakeDigest:
    feed_id: str
    n_sources: int
    feed_hash: str                       # sha256 prefix over the ingested catalog
    verdict_counts: dict                 # {ACTIONABLE, INSPIRATION, NOISE}
    actionable: list[dict] = field(default_factory=list)
    inspiration: list[dict] = field(default_factory=list)
    build_candidates: dict = field(default_factory=dict)  # meta_cycle output
    research_feed: dict = field(default_factory=dict)     # for flywheel.spin()
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "feed_id": self.feed_id,
            "n_sources": self.n_sources,
            "feed_hash": self.feed_hash,
            "verdict_counts": self.verdict_counts,
            "actionable": self.actionable,
            "inspiration": self.inspiration,
            "build_candidates": self.build_candidates,
            "summary": self.summary,
        }


def _feed_hash(catalog: list[dict]) -> str:
    """Content-address the ingested feed so the digest is re-derivable. Keyed on
    the stable (id, text) pairs, order-independent — same content, same hash."""
    payload = sorted(
        (str(row.get("id", "")), str(row.get("text", row.get("title", ""))))
        for row in catalog
    )
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def validate_catalog(catalog: list[dict]) -> list[str]:
    """Curator gate: every row must carry the keys the scout reads. Returns a
    list of problems (empty == clean). Fail loud before ingest, never silently
    drop signal."""
    problems: list[str] = []
    if not isinstance(catalog, list):
        return ["catalog is not a list"]
    seen: set[str] = set()
    for i, row in enumerate(catalog):
        if not isinstance(row, dict):
            problems.append(f"row {i}: not an object")
            continue
        for k in REQUIRED_KEYS:
            if not str(row.get(k, "")).strip():
                problems.append(f"row {i}: missing/empty '{k}'")
        rid = str(row.get("id", ""))
        if rid and rid in seen:
            problems.append(f"row {i}: duplicate id '{rid}'")
        seen.add(rid)
    return problems


def load_feed(path: str | Path) -> tuple[str, list[dict]]:
    """Load a feed file. Accepts either a bare list, or an object with a
    'catalog' list plus metadata. Returns (feed_id, catalog)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return (str(Path(path).stem), data)
    catalog = data.get("catalog", [])
    feed_id = str(data.get("source", Path(path).stem))
    return (feed_id, catalog)


def digest(catalog: list[dict], *, feed_id: str = "feed",
           efficiency_feed: dict | None = None, top_k: int = 6,
           harness_vocab: set[str] | None = None) -> IntakeDigest:
    """Run the full intake pipeline on an in-memory catalog and return the
    digest receipt. `efficiency_feed` (from telemetry) composes here so a single
    meta_cycle ranks BOTH research and efficiency candidates; pass None to score
    research alone."""
    problems = validate_catalog(catalog)
    if problems:
        raise ValueError(f"intake catalog invalid: {problems[:5]}")

    assessments = scout.rank(catalog, harness_vocab)
    feed = scout.synthesize_feed(assessments, top_k=top_k)
    cycle = meta_cycle(feed, efficiency_feed or {},
                       baseline={"source": feed_id, "n": len(catalog)})
    # `feed` is also what flywheel.spin(research_feed=...) consumes — expose it
    # on the digest so one intake drives both evolve and the wheel.

    counts = {"ACTIONABLE": 0, "INSPIRATION": 0, "NOISE": 0}
    for a in assessments:
        counts[a.verdict] = counts.get(a.verdict, 0) + 1

    summary = (
        f"{feed_id}: {len(catalog)} sources -> "
        f"{counts['ACTIONABLE']} actionable, {counts['INSPIRATION']} inspiration, "
        f"{counts['NOISE']} noise; "
        f"{len(cycle.get('auto_apply', []))} auto-config + "
        f"{len(cycle.get('gated', []))} gated build candidate(s)"
    )
    return IntakeDigest(
        feed_id=feed_id,
        n_sources=len(catalog),
        feed_hash=_feed_hash(catalog),
        verdict_counts=counts,
        actionable=feed.get("actionable_threads", []),
        inspiration=feed.get("inspiration_threads", []),
        build_candidates={"auto_apply": cycle.get("auto_apply", []),
                          "gated": cycle.get("gated", []),
                          "surface_only": cycle.get("surface_only", [])},
        research_feed=feed,
        summary=summary,
    )


def digest_feed(path: str | Path, *, efficiency_feed: dict | None = None,
                top_k: int = 6) -> IntakeDigest:
    """Convenience: load a feed file and digest it in one call."""
    feed_id, catalog = load_feed(path)
    return digest(catalog, feed_id=feed_id, efficiency_feed=efficiency_feed,
                  top_k=top_k)


def digest_report(d: IntakeDigest) -> str:
    """Human-readable intake digest — what came in, how it classified, what
    became a build candidate."""
    lines = [f"intake digest — {d.feed_id}",
             f"  feed_hash: {d.feed_hash}  ({d.n_sources} sources)",
             f"  verdicts: {d.verdict_counts['ACTIONABLE']} actionable / "
             f"{d.verdict_counts['INSPIRATION']} inspiration / "
             f"{d.verdict_counts['NOISE']} noise"]
    if d.actionable:
        lines.append("  ACTIONABLE (falsifiable build candidates):")
        for t in d.actionable:
            lines.append(f"    - {t['title']}  [rel={t['relevance']}]")
    gated = d.build_candidates.get("gated", [])
    auto = d.build_candidates.get("auto_apply", [])
    if auto:
        lines.append("  auto-config (self-tunable, falsifier-gated):")
        for c in auto:
            lines.append(f"    - {c['description'][:88]}")
    if gated:
        lines.append("  gated-capability (need admission):")
        for c in gated:
            lines.append(f"    - {c['description'][:88]}")
    return "\n".join(lines)
