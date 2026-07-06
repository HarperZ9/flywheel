"""scout.py — the "sly fox": autonomous research-curation that feeds the build.

Consumes a gather catalog (receipt-backed sources), assesses each for FALSIFIABLE
harness-relevance (the crucible discipline applied at scale), and ranks
actionable threads above inspiration-only above noise. This is the self-recursive
loop's perception arm: the system discovers and isolates threads that imply a
MEASURABLE MECHANISM (a knob, a metric, an ablation), not metaphors.

The sly-fox behavior: a thread is ACTIONABLE only if it is BOTH relevant to the
harness vocabulary AND implies a falsifiable extension (a change with a
pass/fail observation). Relevant-but-metaphorical threads are INSPIRATION
(like AWG's grounding claims — labeled, not proven). Irrelevant is NOISE.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

HARNESS_VOCAB = {
    "verified", "verification", "oracle", "receipt", "cache", "diversity",
    "escalation", "search", "entropy", "option", "quantiz", "tool-use",
    "tool use", "eval", "benchmark", "ablation", "pass@", "best-of-n",
    "reinforcement", "reward", "agent", "harness", "inference", "retrieval",
    "embedding", "attention", "context", "token", "fine-tun", "distill",
    "merge", "ensemble", "delegate", "routing", "calibrat", "selective",
    "uncertain", "abstain", "self-correct", "consensus", "tamper", "chain",
    "locality", "edit", "memory", "compaction", "compress",
    "model", "training", "performance", "accuracy", "speedup", "optimization",
    "parallel", "distributed", "dataset", "transformer", "language model",
    "gradient", "neural", "gpu", "latency", "throughput", "capability",
    "scaling", "efficiency", "compact", "pruning", "sparse", "kernel",
    "shader", "render", "compute", "weight", "local", "offline",
    "federated", "decentralized", "open-source", "open source",
}

FALSIFIABILITY_SIGNALS = {
    "improv", "reduc", "increas", "method", "algorithm", "metric", "measure",
    "ablation", "result", "outperform", "accuracy", "f1", "pass", "score",
    "baseline", "compare", "evaluat", "speedup", "throughput", "latency",
    "budget", "temperature", "rank", "threshold", "parameter", "knob",
}


@dataclass
class ThreadAssessment:
    source_id: str
    title: str
    ref: str
    relevance: float
    falsifiable: bool
    suggested_extension: str
    verdict: str  # ACTIONABLE | INSPIRATION | NOISE

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("source_id", "title", "ref", "relevance", "falsifiable",
                 "suggested_extension", "verdict")}


def _text_of(row: dict) -> str:
    return " ".join(str(row.get(k, "")) for k in
                    ("title", "abstract", "summary", "text")).lower()


# Relevance is COVERAGE (how many distinct harness concepts a thread touches),
# saturating and length-independent — NOT density (hits/word_count), which was
# length-fragile: the same thread flipped ACTIONABLE<->NOISE purely on verbosity.
_SATURATION_K = 5.0
_REL_THRESHOLD = 0.25   # ~ >= 2 distinct concepts under the saturation curve
_MIN_HITS = 2


def _matched(text: str, terms: set[str]) -> list[str]:
    """Terms present at a WORD BOUNDARY (prefix match), so stems still fire
    ("quantiz" -> "quantization") but there are no phantom mid-word hits
    ("merge" in "emergent"). Returns the sorted distinct matches."""
    return sorted(t for t in terms if re.search(r"\b" + re.escape(t), text))


def _hit_terms(text: str, vocab: set[str]) -> list[str]:
    """Distinct harness concepts a thread names (word-boundary matched)."""
    return _matched(text, vocab)


def _relevance(n_hits: int) -> float:
    """Coverage-saturation: diminishing returns on concept count, independent of
    prose length. 2 hits -> 0.29, 4 -> 0.44, 7 -> 0.58."""
    return n_hits / (n_hits + _SATURATION_K)


def assess(row: dict, harness_vocab: set[str] | None = None) -> ThreadAssessment:
    vocab = harness_vocab or HARNESS_VOCAB
    text = _text_of(row)
    hit_terms = _hit_terms(text, vocab)
    hits = len(hit_terms)
    rel = _relevance(hits)
    falsifiable = bool(_matched(text, FALSIFIABILITY_SIGNALS))
    title = str(row.get("title", row.get("id", "untitled")))[:120]
    ref = str(row.get("ref", row.get("id", "")))
    sid = str(row.get("id", ref))
    ext = ""
    if hits >= _MIN_HITS and rel >= _REL_THRESHOLD and falsifiable:
        ext = (f"measurable mechanism touching: {', '.join(hit_terms[:4])} — "
               f"propose a harness knob/ablation and check pass-rate delta")
    relevant = rel >= _REL_THRESHOLD and hits >= _MIN_HITS
    if relevant and falsifiable:
        verdict = "ACTIONABLE"
    elif relevant:
        verdict = "INSPIRATION"
    else:
        verdict = "NOISE"
    return ThreadAssessment(sid, title, ref, round(rel, 3), falsifiable, ext, verdict)


def rank(catalog: list[dict], harness_vocab: set[str] | None = None) -> list[ThreadAssessment]:
    assessed = [assess(r, harness_vocab) for r in catalog]
    order = {"ACTIONABLE": 0, "INSPIRATION": 1, "NOISE": 2}
    return sorted(assessed, key=lambda a: (order[a.verdict], -a.relevance))


def actionable_only(catalog: list[dict], harness_vocab: set[str] | None = None) -> list[ThreadAssessment]:
    return [a for a in rank(catalog, harness_vocab) if a.verdict == "ACTIONABLE"]


def synthesize_feed(assessments: list[ThreadAssessment], *, top_k: int = 5) -> dict:
    """Produce the feed-back artifact: the top actionable threads as build
    candidates, with their suggested extensions. This is what loops back into
    the build pipeline as new todo items."""
    actionable = [a for a in assessments if a.verdict == "ACTIONABLE"][:top_k]
    inspiration = [a for a in assessments if a.verdict == "INSPIRATION"][:top_k]
    return {
        "actionable_threads": [a.to_dict() for a in actionable],
        "inspiration_threads": [a.to_dict() for a in inspiration],
        "noise_count": sum(1 for a in assessments if a.verdict == "NOISE"),
        "feed_summary": (f"{len(actionable)} actionable (falsifiable extensions), "
                         f"{len(inspiration)} inspiration-only, "
                         f"{sum(1 for a in assessments if a.verdict == 'NOISE')} noise"),
    }
