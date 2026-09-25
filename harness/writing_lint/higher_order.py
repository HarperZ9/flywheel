#!/usr/bin/env python3
"""higher_order.py -- the next layer of report-only AI-tell detectors.

The phrase engine in check.py reads vocabulary; structural.py reads a first
layer of rhetorical shape. Human readers still flag prose these two pass as
clean, because the machine tells that survive live in higher-order structure:
affirm-then-negate turns, parallel enumeration, the aphoristic landing beat,
one syntactic frame reused down a page, abstraction with no concrete anchor,
and a metronomic sentence cadence. Each detector operationalizes a rule the
operator's STE standard already states (no corrective negation, no rule of
three or parataxis, no landing sentences, no throat-clearing frames, numbers
that explain, vary sentence length).

Three detectors live here (corrective negation, parallel enumeration,
aphoristic landing); the frame, specificity, and rhythm detectors live in
ho_frames.py; the shared tagger lives in ho_util.py. The orchestrator at the
foot runs all six. Every category is REPORT-ONLY: it steers revision and
regeneration and never gates, the same contract structural.py follows. These
signals score FORM. They are diagnostics for a writer, not a way to defeat AI
detection, which is a non-goal. Standard library only.
"""
from __future__ import annotations

import re

from . import ho_frames as _f
from . import ho_util as U
from .lists import LANDING_TAGS

# Corrective negation, clause-level. ", not X" / ", never X" (affirm then
# retract), "rather than" / "instead of", and the "not X but Y" antithesis.
_COMMA_NEG = re.compile(r",\s+(?:not|never)\b[^.!?;:]{0,40}", re.IGNORECASE)
_RATHER = re.compile(r"\brather than\b|\binstead of\b", re.IGNORECASE)
_NOT_BUT = re.compile(r"\bnot\b[^.!?,;:]{1,60}?\bbut\b", re.IGNORECASE)
_NEG_CUE = re.compile(r"\b(?:not|never|cannot|no)\b|n['’]t\b", re.IGNORECASE)

# Tag phrases sorted longest-first so the alternation counts each landing beat
# once ("and that is the point" is not also counted as "that is the point").
_TAG_RE = re.compile("|".join(re.escape(t) for t in
                              sorted(LANDING_TAGS, key=len, reverse=True)))


def corrective_negation(prose, paras, sents_of):
    """Affirm-then-negate turns, plus adjacent-sentence mirror negation.

    Flags any paragraph carrying two or more. Returns (count, spans,
    paragraphs_flagged).
    """
    spans: "list[str]" = []
    flagged = 0
    total = 0
    for para in paras:
        hits = [m.group(0).strip().rstrip(",")
                for m in _COMMA_NEG.finditer(para)]
        hits += [m.group(0) for m in _RATHER.finditer(para)]
        hits += [m.group(0) for m in _NOT_BUT.finditer(para)]
        mirror = 0
        ps = sents_of(para)
        for a, b in zip(ps, ps[1:]):
            if _NEG_CUE.search(b) and not _NEG_CUE.search(a):
                shared = {s for s in (U.content_stems(a) & U.content_stems(b))
                          if len(s) >= 4}
                if shared:
                    mirror += 1
        pcount = len(hits) + mirror
        total += pcount
        if pcount >= 2:
            flagged += 1
        spans.extend(hits[:4])
    return total, spans[:12], flagged


def _seg_head_class(seg):
    """Lead class of a segment's first content word (leading function words
    skipped), so 'they help price loans' reads as verb-led like 'read scans'."""
    for t in U.toks(seg):
        if t.lower() not in U.FUNCTION:
            return U.lead_class(t)
    tk = U.toks(seg)
    return U.lead_class(tk[0]) if tk else "?"


def _segments(sent):
    """Comma-split a sentence into candidate items, also splitting a final
    'A and B' / 'A or B' when both sides are short (a non-Oxford last pair)."""
    segs = [s.strip() for s in re.split(r",\s*", sent) if s.strip()]
    if segs:
        m = re.match(r"(.+?)\s+(?:and|or)\s+(.+)", segs[-1])
        if m and 1 <= len(U.toks(m.group(1))) <= 4 \
                and 1 <= len(U.toks(m.group(2))) <= 4:
            segs = segs[:-1] + [m.group(1).strip(), m.group(2).strip()]
    return segs


def parallel_enumeration(sents):
    """Comma/and runs of 3+ short items that share a leading part of speech.

    A run is a maximal stretch of consecutive short (1-4 word) segments whose
    head words share a class; long segments are clause material and break a
    run. Returns (run_count, detail) with max_items, the share of sentences
    carrying a run, balanced-tricolon count, and example spans.
    """
    runs = max_items = tricolon_balanced = sents_with_run = 0
    spans: "list[str]" = []
    for sent in sents:
        info = [(1 <= len(U.toks(s)) <= 4, _seg_head_class(s), s)
                for s in _segments(sent)]
        found = False
        i = 0
        while i < len(info):
            if not info[i][0]:
                i += 1
                continue
            j = i
            while j + 1 < len(info) and info[j + 1][0] \
                    and info[j + 1][1] == info[i][1]:
                j += 1
            n = j - i + 1
            if n >= 3 and info[i][1] in ("N", "V", "D", "ADV"):
                runs += 1
                found = True
                max_items = max(max_items, n)
                wcs = [len(U.toks(info[k][2])) for k in range(i, j + 1)]
                if n == 3 and max(wcs) - min(wcs) <= 1:
                    tricolon_balanced += 1
                if len(spans) < 8:
                    spans.append(", ".join(info[k][2]
                                           for k in range(i, j + 1))[:90])
            i = j + 1
        if found:
            sents_with_run += 1
    share = round(sents_with_run / len(sents), 2) if sents else 0.0
    detail = {"runs": runs, "max_items": max_items,
              "share_sentences_with_run": share,
              "tricolon_balanced": tricolon_balanced, "spans": spans}
    return runs, detail


def aphoristic_landing(paras, sents_of, low):
    """Paragraph-final short sentences that restate the opening or hit a tag.

    Returns (count, detail). detail carries the share of multi-sentence
    paragraphs ending on a landing beat and the tag-phrase count anywhere.
    """
    flagged = 0
    multi = 0
    spans: "list[str]" = []
    for para in paras:
        ps = sents_of(para)
        if len(ps) < 2:
            continue
        multi += 1
        lens = [U.wc(s) for s in ps]
        last = ps[-1]
        mean = sum(lens) / len(lens)
        if lens[-1] == 0 or lens[-1] >= mean:
            continue
        overlap = {s for s in (U.content_stems(ps[0]) & U.content_stems(last))
                   if len(s) >= 4}
        distinctive = any(len(s) >= 8 for s in overlap)
        low_last = " ".join(last.lower().split())
        tag = any(t in low_last for t in LANDING_TAGS)
        if len(overlap) >= 2 or distinctive or tag:
            flagged += 1
            if len(spans) < 8:
                spans.append(last[:90])
    tag_hits = len(_TAG_RE.findall(low))
    share = round(flagged / multi, 2) if multi else 0.0
    detail = {"share_paragraphs_landing": share, "tag_phrase_hits": tag_hits,
              "spans": spans}
    return flagged, detail


def higher_order(prose, paras, sents_of, low):
    """Run every higher-order detector; return counts plus per-signal detail.

    counts feed check.py's report-only surface (they never gate). detail is a
    JSON-serializable map the generate-score-regenerate loop reads to target
    the spans it should revise.
    """
    counts: "dict[str, int]" = {}
    detail: "dict[str, dict]" = {}
    all_sents = sents_of(prose)

    cn, cn_spans, cn_paras = corrective_negation(prose, paras, sents_of)
    if cn:
        counts["corrective_negation"] = cn
    detail["corrective_negation"] = {
        "count": cn, "paragraphs_flagged": cn_paras, "spans": cn_spans}

    pe, pe_detail = parallel_enumeration(all_sents)
    if pe:
        counts["parallel_enumeration"] = pe
    detail["parallel_enumeration"] = pe_detail

    al, al_detail = aphoristic_landing(paras, sents_of, low)
    if al:
        counts["aphoristic_landing"] = al
    detail["aphoristic_landing"] = al_detail

    rf, rf_detail = _f.repeated_syntactic_frame(all_sents)
    if rf:
        counts["repeated_syntactic_frame"] = rf
    detail["repeated_syntactic_frame"] = rf_detail

    sf, sf_detail = _f.specificity_floor(prose, paras, low, sents_of)
    if sf:
        counts["specificity_floor"] = sf
    detail["specificity_floor"] = sf_detail

    rv, rv_detail = _f.rhythm_variance(all_sents)
    if rv:
        counts["rhythm_variance"] = rv
    detail["rhythm_variance"] = rv_detail

    return {"counts": counts, "detail": detail}
