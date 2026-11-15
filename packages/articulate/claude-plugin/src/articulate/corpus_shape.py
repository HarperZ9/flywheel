"""Four of the series checks behind corpus.analyze_corpus: section shape,
rhythm, perspective and abstract runs. corpus_checks holds the other four.
"""
from . import corpus_features as cf
from .corpus_checks import _kept, _loc, _protect

T = cf.THRESHOLDS


def _even_sections(ctx, d):
    secs = cf.sections(d["text"])
    value = cf.cv([s["words"] for s in secs])
    if len(secs) < T["section_min"] or value is None or value >= T["section_cv"]:
        return []
    last = cf.blocks(d["text"])[-1]["line_end"]
    counts = ", ".join(str(s["words"]) for s in secs)
    return [ctx["finding"]("corpus/section-symmetry", [d["name"]],
                           [_loc(d["name"], secs[0]["line"], last,
                                 f"{len(secs)} sections, word counts {counts}")],
                           {"kind": "even-sections", "sections": len(secs), "cv": value})]


def _heading_overlap(ctx):
    seen = {}
    for d in ctx["docs"]:
        for s in cf.sections(d["text"]):
            seen.setdefault(cf.heading_key(s["heading"]), {}).setdefault(d["name"], s)
    out, total = [], len(ctx["docs"])
    for key, per_doc in sorted(seen.items()):
        if not key or len(per_doc) < 2 or len(per_doc) / total < T["heading_doc_share"]:
            continue
        if _kept(ctx, key):
            _protect(ctx, "corpus/section-symmetry", key, per_doc)
            continue
        locs = [_loc(n, s["line"], s["line"], s["heading"]) for n, s in per_doc.items()]
        out.append(ctx["finding"]("corpus/section-symmetry", list(per_doc), locs,
                                  {"kind": "heading-overlap", "heading": key,
                                   "docs": len(per_doc)}))
    return out


def section_symmetry(ctx):
    out = []
    for d in ctx["docs"]:
        out += _even_sections(ctx, d)
    return out + ([] if ctx["single"] else _heading_overlap(ctx))


def _doc_rhythm(ctx, d, records):
    lengths = [n for _, n in records]
    out, value = [], cf.cv(lengths)
    if len(lengths) >= T["rhythm_min_sentences"] and value is not None and value < T["rhythm_cv"]:
        out.append(ctx["finding"]("corpus/rhythm", [d["name"]],
                                  [_loc(d["name"], records[0][0], records[-1][0],
                                        f"{len(lengths)} sentences, length CV {value}")],
                                  {"kind": "flat", "cv": value, "sentences": len(lengths)}))
    run, start = cf.longest_band_run(lengths, T["rhythm_band"]) if lengths else (0, 0)
    if run >= T["rhythm_run"]:
        a, b = records[start][0], records[start + run - 1][0]
        out.append(ctx["finding"]("corpus/rhythm", [d["name"]],
                                  [_loc(d["name"], a, b, f"{run} sentences within "
                                        f"{T['rhythm_band']} words of each other")],
                                  {"kind": "even-run", "run": run, "band": T["rhythm_band"]}))
    return out, value if len(lengths) >= T["rhythm_min_sentences"] else None


def rhythm(ctx):
    out, cvs = [], {}
    for d in ctx["docs"]:
        records = cf.sentence_records(d["text"])
        found, value = _doc_rhythm(ctx, d, records)
        out += found
        if value is not None:
            cvs[d["name"]] = (value, records)
    if not ctx["single"] and len(cvs) >= 3:
        values = [v for v, _ in cvs.values()]
        if max(values) - min(values) <= T["rhythm_spread"]:
            locs = [_loc(n, r[0][0], r[-1][0], f"length CV {v}") for n, (v, r) in cvs.items()]
            out.append(ctx["finding"]("corpus/rhythm", list(cvs), locs,
                                      {"kind": "same-cv", "spread": round(max(values) - min(values), 3)}))
    return out


def perspective(ctx):
    if ctx["genre"] not in cf.ARGUED_GENRES:
        return []
    out = []
    for d in ctx["docs"]:
        prose = cf.prose_blocks(d["text"])
        total = sum(len(cf.words(b["text"])) for b in prose)
        singular = sum(cf.first_person(b["text"])[0] for b in prose)
        plural = sum(cf.first_person(b["text"])[1] for b in prose)
        rate = round((singular + plural) * 1000 / total, 2) if total else 0
        if total >= T["perspective_min_words"] and rate < T["perspective_rate"]:
            out.append(ctx["finding"]("corpus/perspective", [d["name"]],
                                      [_loc(d["name"], prose[0]["line_start"], prose[-1]["line_end"],
                                            f"{singular + plural} first-person words in {total}")],
                                      {"kind": "rate", "per_1k": rate, "words": total}))
        for n, a, b in cf.author_stretches(d["text"]):
            if n > T["perspective_stretch"]:
                out.append(ctx["finding"]("corpus/perspective", [d["name"]],
                                          [_loc(d["name"], a, b, f"{n} words with no first person")],
                                          {"kind": "stretch", "words": n}))
    return out


def abstract_run(ctx):
    out = []
    for d in ctx["docs"]:
        for a, b, n in cf.abstract_runs(d["text"], T["abstract_run"])[:5]:
            out.append(ctx["finding"]("corpus/abstract-run", [d["name"]],
                                      [_loc(d["name"], a, b, f"{n} paragraphs with no name, "
                                            "number, place or quotation")],
                                      {"paragraphs": n}))
    return out


CHECKS = [section_symmetry, rhythm, perspective, abstract_run]
