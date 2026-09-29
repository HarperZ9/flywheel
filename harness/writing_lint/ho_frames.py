#!/usr/bin/env python3
"""ho_frames.py -- higher-order detectors for frame, specificity, and rhythm.

Three of the six next-layer tells: one syntactic frame reused down a page,
abstraction with no concrete anchor, and a metronomic sentence cadence. Each
operationalizes a rule the STE standard states (no throat-clearing frames,
numbers that explain, vary sentence length). Report-only, never gates.
Standard library only.
"""
from __future__ import annotations

import math
import re

from . import ho_util as U
from .lists import (
    AUX_BE, DETERMINERS, UNQUANTIFIED_MAGNITUDE, UNSOURCED_AUTHORITY,
)

# A number token, currency symbol and thousands separators included, so
# "$4,200" reads as one anchored figure rather than a bare "4" and "200".
_NUMTOK = re.compile(r"[$£€]?\d[\d,]*(?:\.\d+)?")
# Context that anchors a number as a concrete measurement or a real
# denominator/interval, so it is NOT an unsupported magnitude claim.
_ANCHORED = re.compile(
    r"[$£€%/]|±|\+/-|a\.m\.|p\.m\.|\bpercent\b|\bper\b|\bof\b"
    r"|\bout of\b|\binterval\b|\bCI\b|\bn\s*=|\b(?:feet|foot|ft|inch|inches|cm|"
    r"mm|km|meter|meters|mile|miles|hour|hours|hr|minute|minutes|min|second|"
    r"seconds|sec|day|days|week|weeks|month|months|year|years|yr|kg|lb|lbs|mph|"
    r"degrees|dollars|cents|am|pm)\b", re.IGNORECASE)
_MONTHS = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b")
_ACRONYM = re.compile(r"\b[A-Z]{2,}\b")
_QUOTE = re.compile(r"[\"“][^\"”]{3,}[\"”]")
_DATE = re.compile(r"\b\d{1,4}[-/]\d{1,2}(?:[-/]\d{1,4})?\b")
_PROPER = re.compile(r"[A-Z][a-z]+")


def _frame_key(sent):
    tk = U.toks(sent)
    if not tk:
        return None, False
    low = [t.lower() for t in tk]
    if low[0] == "what" and any(t in AUX_BE for t in low[1:8]):
        return "WHAT-CLEFT", True
    if len(low) >= 2 and low[0] == "it" and low[1] in ("is", "was"):
        return "IT-BE", True
    if len(low) >= 2 and low[0] == "there" and low[1] in ("is", "are", "was",
                                                          "were"):
        return "THERE-EXIST", True
    if len(low) >= 2 and low[0] in ("this", "that") and low[1] in ("is", "was"):
        return "DEM-BE:" + low[0], True
    run = []
    for t in low[:3]:
        if t in U.FUNCTION:
            run.append(t)
        else:
            break
    if run:
        key = "FW:" + " ".join(run)
        if len(run) == 1 and run[0] in DETERMINERS and len(tk) > 1:
            key += "+" + U.lead_class(tk[1])
        return key, False
    return "OPEN:" + U.lead_class(tk[0], True), False


def repeated_syntactic_frame(sents):
    """Bucket sentences by opening template; flag any used 3+ times.

    Pseudo-cleft and existential openers weigh highest. Returns
    (flagged_template_count, detail).
    """
    counts: "dict[str, int]" = {}
    cleft: "dict[str, bool]" = {}
    for sent in sents:
        key, is_cleft = _frame_key(sent)
        if key is None:
            continue
        counts[key] = counts.get(key, 0) + 1
        cleft[key] = is_cleft
    flagged = {k: n for k, n in counts.items() if n >= 3}
    weight = 0
    for k, n in flagged.items():
        weight += n * (3 if k.endswith("CLEFT") else 2 if cleft[k] else 1)
    detail = {"frames": flagged, "weighted_score": weight,
              "cleft_frames": sorted(k for k in flagged if cleft[k])}
    return len(flagged), detail


def _anchor_count(para, sents_of):
    n = len(_NUMTOK.findall(para)) + len(_ACRONYM.findall(para))
    n += len(_QUOTE.findall(para)) + len(_DATE.findall(para))
    for s in sents_of(para):
        n += sum(1 for t in U.toks(s)[1:] if _PROPER.fullmatch(t))
    return n


def specificity_floor(prose, paras, low, sents_of):
    """Concrete-anchor density and an unsupported-claim scan.

    count sums anchorless paragraphs, unsourced-authority and
    unquantified-magnitude phrases, and bare number claims. Returns
    (count, detail).
    """
    anchorless = 0
    anchors = 0
    for para in paras:
        n = _anchor_count(para, sents_of)
        anchors += n
        if n == 0:
            anchorless += 1
    words = U.wc(prose) or 1
    auth = U.phrase_hits(low, UNSOURCED_AUTHORITY)
    mag = U.phrase_hits(low, UNQUANTIFIED_MAGNITUDE)
    bare = 0
    for m in _NUMTOK.finditer(prose):
        val = m.group(0)
        if val[0] in "$£€":
            continue                       # currency-anchored, a real figure
        digits = val.replace(",", "").split(".")[0]
        if digits.isdigit() and 1800 <= int(digits) <= 2100:
            continue                       # a year, not a magnitude claim
        window = prose[max(0, m.start() - 14): m.end() + 14]
        if _ANCHORED.search(window) or _MONTHS.search(window):
            continue
        bare += 1
    count = anchorless + len(auth) + len(mag) + bare
    detail = {"anchorless_paragraphs": anchorless, "paragraphs": len(paras),
              "anchor_density_per100w": round(anchors * 100.0 / words, 2),
              "unsourced_authority": auth, "unquantified_magnitude": mag,
              "bare_number_claims": bare}
    return count, detail


def rhythm_variance(sents):
    """Sentence-length dispersion and metronome runs.

    A low coefficient of variation, a long run of near-equal-length sentences,
    or a long run of the same opening part of speech each counts as one
    metronomic flag. Returns (flag_count, detail).
    """
    lens = [n for n in (U.wc(s) for s in sents) if n > 0]
    if len(lens) < 5:
        return 0, {"cv": None, "stdev": None, "flags": []}
    mean = sum(lens) / len(lens)
    stdev = math.sqrt(sum((n - mean) ** 2 for n in lens) / len(lens))
    cv = stdev / mean if mean else 0.0
    band_run = U.longest_band_run(lens, 4)
    poss = [U.coarse_pos(U.toks(s)[0], True) if U.toks(s) else "OTHER"
            for s in sents]
    pos_run = U.longest_equal_run(poss)
    flags = []
    if cv < 0.40:
        flags.append("low_cv")
    if band_run >= 5:
        flags.append("even_band_run")
    if pos_run >= 4:
        flags.append("same_opening_pos_run")
    detail = {"cv": round(cv, 2), "stdev": round(stdev, 2),
              "mean_words": round(mean, 1),
              "longest_same_band_run": band_run,
              "longest_same_opening_pos_run": pos_run, "flags": flags}
    return len(flags), detail
