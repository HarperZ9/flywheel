"""The digest receipt: content-addressed over inputs and method, re-derivable.

verify() recomputes the deterministic pipeline (lexicon score -> cluster -> weight
-> themes) from the same inputs and confirms the digest hash. Model-pass scores,
when they exist in later phases, are excluded from this deterministic re-derivation
and listed with their own provenance, so the receipt is honest about which parts a
stranger can re-check and which are model opinion.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from dataclasses import dataclass

from chorus.sentiment import Scored, lexicon_vocab_sha

METHOD_VERSION = "chorus-lens/3"   # /3 added corpus-salience labels + label_quality to the body
SUPPORTED_METHOD_VERSIONS = frozenset(("chorus-lens/2", METHOD_VERSION))


@dataclass(frozen=True)
class DigestReceipt:
    input_sha256: str
    lexicon_vocab_sha: str
    cluster_params: dict
    weight_formula: dict
    model_ref: str | None
    digest_sha256: str
    method_version: str


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def input_digest(scored: list[Scored]) -> str:
    return _sha([[s.item.id, s.item.engagement, s.item.text] for s in scored])


def digest_body_sha(digest, *, method_version: str | None = None) -> str:
    version = method_version
    if version is None:
        version = getattr(getattr(digest, "receipt", None), "method_version", METHOD_VERSION)
    if version == "chorus-lens/2":
        body = [[t.label, list(t.item_ids), t.weighted_score,
                 t.sentiment, t.representative, t.dissent, t.controversy] for t in digest.themes]
    elif version == METHOD_VERSION:
        body = [[t.label, list(t.terms), t.label_quality, list(t.item_ids), t.weighted_score,
                 t.sentiment, t.representative, t.dissent, t.controversy] for t in digest.themes]
    else:
        raise ValueError(f"unsupported method version: {version}")
    contested = [[c["term"], c["mentions"], c["pos"], c["neg"], c["contested"]]
                 for c in digest.contested]
    return _sha([digest.responds_to, digest.n_items, digest.method, body, contested])


def build_receipt(scored: list[Scored], digest, *, model_ref: str | None = None) -> DigestReceipt:
    m = digest.method
    return DigestReceipt(
        input_sha256=input_digest(scored),
        lexicon_vocab_sha=lexicon_vocab_sha(),
        cluster_params={"threshold": m["cluster_threshold"], "dims": m["dims"],
                        "pos_cut": m["pos_cut"], "neg_cut": m["neg_cut"],
                        "aspect_min_mentions": m["aspect_min_mentions"],
                        "aspect_top_k": m["aspect_top_k"]},
        weight_formula={"expr": "log1p(engagement)*(1+k*abs(compound))", "k": m["weight_k"]},
        model_ref=model_ref,
        digest_sha256=digest_body_sha(digest),
        method_version=METHOD_VERSION,
    )


def _legacy_v2_label(top_terms):
    return " / ".join(top_terms[:3]) if top_terms else "(untitled theme)"


def _legacy_v2_build_theme(group, *, k, pos_cut, neg_cut):
    from chorus.synthesize import Theme, _terms, item_weight
    weighted = [(s, item_weight(s.item.engagement, s.compound, k=k)) for s in group]
    term_counts = Counter(t for s in group for t in _terms(s.item.text))
    top_terms = [t for t, _ in term_counts.most_common(5)]
    pos = sum(1 for s in group if s.compound >= pos_cut)
    neg = sum(1 for s in group if s.compound <= neg_cut)
    neu = len(group) - pos - neg
    n = len(group)
    majority_pos = pos >= neg
    minority = [(s, w) for s, w in weighted
                if ((s.compound <= neg_cut) if majority_pos else (s.compound >= pos_cut))]
    dissent = max(minority, key=lambda sw: sw[1])[0].item.id if minority else None
    representative = max(weighted, key=lambda sw: sw[1])[0].item.id
    controversy = round(statistics.pstdev([s.compound for s in group]), 4) if n > 1 else 0.0
    return Theme(
        label=_legacy_v2_label(top_terms),
        terms=tuple(top_terms),
        size=n,
        weighted_score=round(sum(w for _, w in weighted), 4),
        sentiment={"pos": round(pos / n, 3), "neg": round(neg / n, 3),
                   "neu": round(neu / n, 3),
                   "mean_compound": round(sum(s.compound for s in group) / n, 4)},
        representative=representative,
        dissent=dissent,
        item_ids=tuple(s.item.id for s in group),
        label_quality={},
        controversy=controversy,
    )


def _legacy_v2_synthesize(scored: list[Scored], *, k: float, threshold: float, dims: int,
                          pos_cut: float, neg_cut: float, aspect_min_mentions: int,
                          aspect_top_k: int):
    from chorus.synthesize import Digest, _COARSENESS, _responds_to, cluster, contested_aspects
    groups = cluster(scored, threshold=threshold, dims=dims)
    themes = [_legacy_v2_build_theme(g, k=k, pos_cut=pos_cut, neg_cut=neg_cut) for g in groups]
    themes.sort(key=lambda t: t.weighted_score, reverse=True)
    present = sum(1 for s in scored if s.item.meta.get("engagement_present"))
    return Digest(
        responds_to=_responds_to(scored), n_items=len(scored), themes=tuple(themes),
        method={"weight_k": k, "cluster_threshold": threshold, "dims": dims,
                "pos_cut": pos_cut, "neg_cut": neg_cut,
                "aspect_min_mentions": aspect_min_mentions, "aspect_top_k": aspect_top_k,
                "engagement_coverage": {"present": present, "total": len(scored)},
                "distinct_targets": len({s.item.responds_to for s in scored}),
                "coarseness": _COARSENESS},
        contested=contested_aspects(scored, pos_cut=pos_cut, neg_cut=neg_cut,
                                    min_mentions=aspect_min_mentions, top_k=aspect_top_k),
    )


def _rederive_digest(method_version: str, scored: list[Scored], receipt: DigestReceipt):
    from chorus.sentiment import score as _score
    from chorus.synthesize import _ASPECT_MIN_MENTIONS, _ASPECT_TOP_K
    cp = receipt.cluster_params
    kwargs = dict(
        k=receipt.weight_formula["k"], threshold=cp["threshold"], dims=cp["dims"],
        pos_cut=cp["pos_cut"], neg_cut=cp["neg_cut"],
        # re-derive contestedness from the RECORDED aspect params, not live constants,
        # so bumping a default cannot silently break an already-versioned receipt
        aspect_min_mentions=cp.get("aspect_min_mentions", _ASPECT_MIN_MENTIONS),
        aspect_top_k=cp.get("aspect_top_k", _ASPECT_TOP_K),
    )
    rescored = _score([s.item for s in scored])
    if method_version == "chorus-lens/2":
        return _legacy_v2_synthesize(rescored, **kwargs)
    if method_version == METHOD_VERSION:
        from chorus.synthesize import synthesize as _synthesize
        return _synthesize(rescored, **kwargs)
    raise ValueError(f"unsupported method version: {method_version}")


def verify(digest, scored: list[Scored]) -> bool:
    """Re-derive the whole deterministic digest from the INPUTS and the receipt-recorded params,
    then confirm the digest body hash. Read-only.

    This is the receipt's promise: a stranger holding the same corpus re-runs the pipeline and gets
    the same digest, or the digest is rejected. It re-scores sentiment from each item's text (the
    caller's `compound` is ignored, so fabricated sentiment cannot verify), re-clusters, and
    re-weights using the params the receipt recorded, then compares hashes. A digest whose themes,
    weights, or sentiment distribution do not follow from the inputs fails, even if its own stored
    digest_sha256 was recomputed to match its tampered body.
    """
    r = digest.receipt
    if r is None:
        return False
    if r.method_version not in SUPPORTED_METHOD_VERSIONS:
        return False
    if r.lexicon_vocab_sha != lexicon_vocab_sha():
        return False
    if r.input_sha256 != input_digest(scored):
        return False
    try:
        if digest_body_sha(digest, method_version=r.method_version) != r.digest_sha256:
            return False
        rederived = _rederive_digest(r.method_version, scored, r)
        return digest_body_sha(rederived, method_version=r.method_version) == r.digest_sha256
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
