"""Near-duplicate and template clustering for a batch of short texts.

Similarity uses character 5-gram shingles over normalized text, so it works the
same way in any script and does not depend on word boundaries. MinHash with
banded locality-sensitive hashing proposes candidate pairs; each candidate is
checked with exact Jaccard similarity before it joins a cluster, so the hash only
saves time and never decides membership.

For each cluster, skeleton() aligns the members word by word and keeps the
tokens they share; the gaps become `{}` slots, and each member's fillers are
listed. Standard library only. Deterministic: the hash seeds are fixed.
"""
import difflib
import hashlib
import re
from itertools import combinations

K = 5
NUM_PERM = 64
BANDS = 16
_P = (1 << 61) - 1
_SEEDS = [(1 + 2 * i * 2654435761 % _P, 7 + i * 40503 % _P) for i in range(NUM_PERM)]
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_HANDLE = re.compile(r"@\w+")
_WORD = re.compile(r"[^\s]+")


def normalize(text):
    t = _URL.sub(" <url> ", text)
    t = _HANDLE.sub(" <@> ", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def shingles(text, k=K):
    t = normalize(text)
    if len(t) <= k:
        return {t} if t else set()
    return {t[i:i + k] for i in range(len(t) - k + 1)}


def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _h(s):
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")


def minhash(sh):
    if not sh:
        return [0] * NUM_PERM
    base = [_h(s) for s in sh]
    return [min((a * x + b) % _P for x in base) for a, b in _SEEDS]


def _candidates(sigs):
    rows = NUM_PERM // BANDS
    pairs = set()
    for band in range(BANDS):
        buckets = {}
        for i, sig in enumerate(sigs):
            key = tuple(sig[band * rows:(band + 1) * rows])
            buckets.setdefault(key, []).append(i)
        for ids in buckets.values():
            pairs.update(combinations(ids, 2))
    return pairs


def _find(parent, i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def cluster(texts, threshold=0.5, min_size=2):
    """Group texts whose shingle Jaccard similarity reaches `threshold`.

    Returns clusters (largest first) as dicts with member indexes and the lowest
    and highest verified pairwise similarity on an edge that joined them.
    """
    sh = [shingles(t) for t in texts]
    sigs = [minhash(s) for s in sh]
    parent = list(range(len(texts)))
    edges = {}
    for i, j in sorted(_candidates(sigs)):
        if not sh[i] or not sh[j]:
            continue
        sim = jaccard(sh[i], sh[j])
        if sim >= threshold:
            edges[(i, j)] = sim
            parent[_find(parent, i)] = _find(parent, j)
    groups = {}
    for i in range(len(texts)):
        groups.setdefault(_find(parent, i), []).append(i)
    out = []
    for members in groups.values():
        if len(members) < min_size:
            continue
        ms = set(members)
        sims = [s for (i, j), s in edges.items() if i in ms]
        out.append({"members": sorted(members), "size": len(members),
                    "similarity_min": round(min(sims), 3), "similarity_max": round(max(sims), 3)})
    out.sort(key=lambda c: (-c["size"], c["members"][0]))
    return out


def _tokens(text):
    return _WORD.findall(normalize(text))


def _align(skel, toks):
    """Keep the tokens of `skel` that also appear, in order, in `toks`; gaps become None."""
    sm = difflib.SequenceMatcher(a=skel, b=toks, autojunk=False)
    out, ai, bi = [], 0, 0
    for a, b, n in sm.get_matching_blocks():
        if a > ai or b > bi:
            out.append(None)
        out.extend(skel[a:a + n])
        ai, bi = a + n, b + n
    merged = []
    for t in out:
        if t is None and merged and merged[-1] is None:
            continue
        merged.append(t)
    return merged


def _fill(skel, toks):
    """Each member's fillers for the `{}` slots of a finished skeleton."""
    lits = [t for t in skel if t is not None]
    sm = difflib.SequenceMatcher(a=lits, b=toks, autojunk=False)
    fills, bi = [], 0
    for _, b, n in sm.get_matching_blocks():
        if b > bi:
            fills.append(" ".join(toks[bi:b]))
        bi = b + n
    return fills


def skeleton(texts):
    """The shared word skeleton of a set of texts, with per-member slot fillers."""
    toks = [_tokens(t) for t in texts]
    if not toks:
        return {"skeleton": "", "shared_tokens": 0, "fillers": []}
    skel = list(toks[0])
    for t in toks[1:]:
        skel = _align(skel, t)
    shared = sum(1 for t in skel if t is not None)
    return {"skeleton": " ".join("{}" if t is None else t for t in skel),
            "shared_tokens": shared,
            "fillers": [_fill(skel, t) for t in toks]}
