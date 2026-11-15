"""Four of the series checks behind corpus.analyze_corpus: titles, phrases,
style habits and paragraph moves. corpus_shape holds the other four.

Each check takes the shared context (documents, keep list, genre, single mode,
the protected list and the finding builder) and returns finding records. The
triggers come from corpus_features.THRESHOLDS.
"""
from . import corpus_features as cf
from . import detector, titles
from .wordlists import FUNCTION_WORDS

T = cf.THRESHOLDS


def _loc(doc, start, end, excerpt):
    first = " ".join(str(excerpt).split())
    return {"doc": doc, "line_start": start, "line_end": max(start, end),
            "excerpt": first[:117] + "..." if len(first) > 120 else first}


def _need(ctx):
    return T["ngram_docs_small"] if len(ctx["docs"]) <= 3 else T["ngram_docs"]


def _kept(ctx, text):
    low = " ".join(text.lower().split())
    return any(k.lower() in low or low in k.lower() for k in ctx["keep"])


def _protect(ctx, category, text, docs):
    ctx["protected"].append({"category": category, "text": text, "docs": sorted(set(docs))})


def _title_line(doc):
    for i, line in enumerate(doc["text"].splitlines(), 1):
        if doc["title"] and doc["title"] in line:
            return i
    return 1


def title_formula(ctx):
    if ctx["single"]:
        return []
    docs = [d for d in ctx["docs"] if d["title"] and not _kept(ctx, d["title"])]
    by_title = {d["title"]: d for d in docs}
    out = []
    for fam in titles.repeated(titles.families(list(by_title)), len(by_title)):
        members = [by_title[t] for t in fam["titles"]]
        out.append(ctx["finding"]("corpus/title-formula", [d["name"] for d in members],
                                  [_loc(d["name"], _title_line(d), _title_line(d), d["title"])
                                   for d in members],
                                  {"family": fam["family"], "titles": fam["titles"],
                                   "share": fam["share"], "head_words": fam["head_words"]}))
    return out


def _tokens(doc):
    out = []
    for b in cf.prose_blocks(doc["text"]):
        for offset, line in enumerate(b["text"].splitlines()):
            out += [(w.lower(), b["line_start"] + offset) for w in cf.words(line)]
    return out


def _grams(tokens, n):
    found = {}
    for i in range(len(tokens) - n + 1):
        gram = tuple(t for t, _ in tokens[i:i + n])
        if sum(w not in FUNCTION_WORDS for w in gram) >= 2:
            found.setdefault(gram, i)
    return found


def _spans(tokens, qualifying, n):
    """Maximal runs of consecutive qualifying n-gram starts, as token ranges."""
    starts = sorted(i for i in range(len(tokens) - n + 1)
                    if tuple(t for t, _ in tokens[i:i + n]) in qualifying)
    runs = []
    for i in starts:
        if runs and i <= runs[-1][1]:
            runs[-1][1] = i + n
        else:
            runs.append([i, i + n])
    return runs


def shared_ngram(ctx):
    if ctx["single"]:
        return []
    n, need = T["ngram_min"], _need(ctx)
    streams = {d["name"]: _tokens(d) for d in ctx["docs"]}
    counts = {}
    for toks in streams.values():
        for gram in _grams(toks, n):
            counts[gram] = counts.get(gram, 0) + 1
    qualifying = {g for g, c in counts.items() if c >= need}
    joined = {name: " " + " ".join(t for t, _ in toks) + " " for name, toks in streams.items()}
    seen, out = [], []
    for name, toks in streams.items():
        for a, b in _spans(toks, qualifying, n):
            text = " ".join(t for t, _ in toks[a:b])
            if any(text in s for s in seen):
                continue
            seen.append(text)
            docs = [m for m, j in joined.items() if " " + text + " " in j]
            if len(docs) < need:
                continue
            if _kept(ctx, text):
                _protect(ctx, "corpus/shared-ngram", text, docs)
                continue
            locs = [_loc(m, l, l, text) for m in docs
                    for l in [_first_line(streams[m], text.split())]]
            out.append(ctx["finding"]("corpus/shared-ngram", docs, locs,
                                      {"gram": text, "docs": len(docs), "words": b - a}))
    out.sort(key=lambda f: (-f["measure"]["docs"], -f["measure"]["words"]))
    return out[:T["ngram_report"]]


def _first_line(tokens, words):
    k = len(words)
    for i in range(len(tokens) - k + 1):
        if [t for t, _ in tokens[i:i + k]] == words:
            return tokens[i][1]
    return 1


def shared_construction(ctx):
    if ctx["single"]:
        return []
    hits = {}
    for d in ctx["docs"]:
        r = detector.check_text(d["text"])
        for f in r["high"] + r["medium"] + r["low"]:
            hits.setdefault(f["category"], {}).setdefault(d["name"], f)
    out, total = [], len(ctx["docs"])
    for cat, per_doc in sorted(hits.items()):
        if len(per_doc) >= 2 and len(per_doc) / total >= T["construction_doc_share"]:
            locs = [_loc(name, f["line"], f["line"], f.get("snippet") or f.get("match") or cat)
                    for name, f in per_doc.items()]
            out.append(ctx["finding"]("corpus/shared-construction", list(per_doc), locs,
                                      {"style_category": cat, "docs": len(per_doc),
                                       "share": round(len(per_doc) / total, 3)}))
    return out


def _paragraphs(doc):
    return [(b, cf.move_sequence(b["text"])) for b in cf.prose_blocks(doc["text"])
            if len(cf.sentences(b["text"])) >= 2]


def paragraph_scaffold(ctx):
    out, windows = [], {}
    for d in ctx["docs"]:
        paras = _paragraphs(d)
        scaffold = [(b, seq) for b, seq in paras if cf.is_scaffold(seq)]
        share = len(scaffold) / len(paras) if paras else 0
        if len(paras) >= T["scaffold_min_paragraphs"] and share >= T["scaffold_share"]:
            out.append(ctx["finding"]("corpus/paragraph-scaffold", [d["name"]],
                                      [_loc(d["name"], b["line_start"], b["line_end"], b["text"])
                                       for b, _ in scaffold],
                                      {"kind": "limit-endings", "share": round(share, 3),
                                       "paragraphs": len(paras), "scaffold_paragraphs": len(scaffold)}))
        for b, seq in paras:
            for i in range(len(seq) - 2):
                w = tuple(seq[i:i + 3])
                if sum(m in cf.SCAFFOLD_MOVES for m in w) >= 2:
                    windows.setdefault(w, {}).setdefault(d["name"], b)
    if not ctx["single"]:
        need = min(T["scaffold_sequence_docs"], len(ctx["docs"]))
        for w, per_doc in sorted(windows.items()):
            if len(per_doc) >= max(2, need):
                locs = [_loc(n, b["line_start"], b["line_end"], b["text"]) for n, b in per_doc.items()]
                out.append(ctx["finding"]("corpus/paragraph-scaffold", list(per_doc), locs,
                                          {"kind": "shared-sequence", "sequence": list(w),
                                           "docs": len(per_doc)}))
    return out


CHECKS = [title_formula, shared_ngram, shared_construction, paragraph_scaffold]
