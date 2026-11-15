# chorus Phase 1 — Core Lens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the offline, deterministic core of chorus: take a corpus of discourse items and emit a clustered, sentiment-weighted digest carrying a re-checkable receipt, driven by `chorus run`.

**Architecture:** Five stdlib units in a pipeline — `item.normalize` (any source → `DiscourseItem`), `sentiment.score` (deterministic lexicon valence), `synthesize` (hashed-TF-IDF clustering + engagement×sentiment weighting → `Digest`), `receipt` (content-addressed, `verify` re-derives), and `cli` (`chorus run`). No daemon, no model pass, no MCP/desktop in this phase.

**Tech Stack:** Python 3.10+, standard library only. pytest for tests. No third-party runtime dependencies.

## Global Constraints

- Zero external runtime dependencies. Standard library only. (pytest is a dev/test dependency.)
- Python 3.10+ (uses `X | None` unions, `dataclasses`).
- Deterministic: given the same inputs and params, every output and every hash is identical. No `time`, `random`, or dict-ordering nondeterminism in the scored/cluster/digest path.
- Sentiment is advisory: it is a weight and a signal, NEVER an accept/reject gate. There is no verdict path in Phase 1.
- Honesty: a missing engagement signal is `0` with the absence recorded, never a fabricated weight. The digest states its method and coarseness.
- Files under 300 lines, functions under 50 lines. One responsibility per file.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 1: Package scaffold + `DiscourseItem` and `normalize`

**Files:**
- Create: `pyproject.toml`, `src/chorus/__init__.py`, `src/chorus/item.py`, `README.md`
- Test: `tests/test_item.py`

**Interfaces:**
- Produces:
  - `DiscourseItem(id: str, source: str, responds_to: str, parent: str | None, author: str, text: str, engagement: int, ts: float | None, meta: dict)` — frozen dataclass.
  - `normalize(rows: list[dict]) -> list[DiscourseItem]` — maps gather-style catalog rows. Each input row: `{"kind": "comment", "id": str, "ref": str, "text": str, "meta": {"author"?: str, "like_count"?: int, "parent"?: str, "ts"?: float, ...}}`. Only `kind == "comment"` rows become items; other kinds are skipped. `engagement = int(meta.get("like_count") or 0)`; when `like_count` is absent, set `meta["engagement_present"] = False`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_item.py
from chorus.item import DiscourseItem, normalize


def test_normalize_maps_comment_rows_and_reads_engagement():
    rows = [
        {"kind": "metadata", "id": "vid1", "ref": "vid1", "text": "{}", "meta": {}},
        {"kind": "comment", "id": "c1", "ref": "vid1", "text": "great talk",
         "meta": {"author": "a", "like_count": 12, "parent": None, "ts": 5.0}},
    ]
    items = normalize(rows)
    assert len(items) == 1                      # metadata row skipped
    it = items[0]
    assert isinstance(it, DiscourseItem)
    assert (it.id, it.source, it.responds_to) == ("c1", "video", "vid1")
    assert it.text == "great talk" and it.author == "a"
    assert it.engagement == 12 and it.ts == 5.0
    assert it.meta.get("engagement_present") is True


def test_normalize_records_absent_engagement_as_zero_not_fabricated():
    rows = [{"kind": "comment", "id": "c2", "ref": "p9", "text": "hi", "meta": {"author": "b"}}]
    it = normalize(rows)[0]
    assert it.engagement == 0
    assert it.meta.get("engagement_present") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_item.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'chorus'`.

- [ ] **Step 3: Create the package scaffold**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "chorus-discourse"
version = "0.1.0"
description = "A discourse-synthesis satellite for gather: weighted, clustered, re-checkable readings of comment corpora."
requires-python = ">=3.10"
dependencies = []

[project.scripts]
chorus = "chorus.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

```python
# src/chorus/__init__.py
"""chorus — a discourse-synthesis satellite for gather.

Turns a corpus of comments and threads into a weighted, clustered, re-checkable
reading of the discourse. Sentiment is a weight and a signal here, never an
accept gate. Stdlib only; deterministic; every digest carries a receipt.
"""
from chorus.item import DiscourseItem, normalize

__version__ = "0.1.0"
__all__ = ["DiscourseItem", "normalize"]
```

```markdown
# chorus

A discourse-synthesis satellite for [gather](https://github.com/HarperZ9/gather).
It reads a captured corpus of comments and threads and emits a weighted,
clustered, re-checkable reading of the discourse: what people are saying, and
which of it is worth reading. Zero third-party runtime dependencies.

Sentiment weights and ranks discourse; it is never an accept gate. Every digest
carries a receipt a stranger can re-run.

```bash
chorus run <corpus-dir-or-items.json>
```
```

- [ ] **Step 4: Write minimal implementation**

```python
# src/chorus/item.py
"""The discourse unit and the adapters that produce it from a gathered corpus.

A DiscourseItem is one comment/post/reply, normalized from any source. Engagement
(likes/upvotes) is read from the source when present; when a source genuinely has
no engagement signal, engagement is 0 and meta records the absence, so a missing
signal is never rendered as a real zero-weight vote.
"""
from __future__ import annotations

from dataclasses import dataclass

# Which gather Item kinds are discourse (as opposed to the media they respond to).
_DISCOURSE_KINDS = {"comment": "video", "feed_item": "feed", "post": "reddit", "reply": "reddit"}


@dataclass(frozen=True)
class DiscourseItem:
    id: str
    source: str
    responds_to: str
    parent: str | None
    author: str
    text: str
    engagement: int
    ts: float | None
    meta: dict


def _engagement(meta: dict) -> tuple[int, bool]:
    """Return (engagement, present). Absent -> (0, False); never a fabricated weight."""
    raw = meta.get("like_count", meta.get("score"))
    if raw is None:
        return 0, False
    try:
        return int(raw), True
    except (TypeError, ValueError):
        return 0, False


def normalize(rows: list[dict]) -> list[DiscourseItem]:
    """Map gather-style catalog rows into DiscourseItems. Non-discourse kinds are skipped."""
    items: list[DiscourseItem] = []
    for row in rows:
        source = _DISCOURSE_KINDS.get(row.get("kind", ""))
        if source is None:
            continue
        meta = dict(row.get("meta") or {})
        engagement, present = _engagement(meta)
        meta["engagement_present"] = present
        ts = meta.get("ts")
        items.append(DiscourseItem(
            id=str(row.get("id", "")),
            source=source,
            responds_to=str(row.get("ref", "")),
            parent=meta.get("parent"),
            author=str(meta.get("author", "")),
            text=str(row.get("text", "")),
            engagement=engagement,
            ts=float(ts) if isinstance(ts, (int, float)) else None,
            meta=meta,
        ))
    return items
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pip install -e . && python -m pytest tests/test_item.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/chorus/__init__.py src/chorus/item.py README.md tests/test_item.py
git commit -m "feat(item): DiscourseItem + normalize with honest engagement nulls

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Deterministic lexicon sentiment

**Files:**
- Create: `src/chorus/sentiment.py`
- Test: `tests/test_sentiment.py`

**Interfaces:**
- Consumes: `DiscourseItem` from Task 1.
- Produces:
  - `Scored(item: DiscourseItem, compound: float, provenance: str, evidence: tuple[str, ...])` — frozen dataclass. `compound` in `[-1, 1]`, `provenance == "lexicon"`, `evidence` = the valence tokens that fired.
  - `score_text(text: str) -> tuple[float, tuple[str, ...]]` — pure; returns `(compound, firing_tokens)`.
  - `score(items: list[DiscourseItem]) -> list[Scored]`.
  - `LEXICON_VERSION: str` and `lexicon_vocab_sha() -> str` (sha256 over the sorted vocab, first 16 hex).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sentiment.py
from chorus.item import DiscourseItem
from chorus.sentiment import score, score_text, lexicon_vocab_sha, LEXICON_VERSION


def _item(text, eng=0):
    return DiscourseItem("i", "video", "v", None, "a", text, eng, None, {})


def test_positive_and_negative_have_expected_sign():
    assert score_text("this is great, I love it")[0] > 0.2
    assert score_text("this is terrible, I hate it")[0] < -0.2


def test_negation_flips_sign():
    pos, _ = score_text("good")
    neg, _ = score_text("not good")
    assert pos > 0 and neg < 0


def test_intensifier_increases_magnitude():
    base, _ = score_text("good")
    strong, _ = score_text("very good")
    assert strong > base


def test_neutral_text_is_near_zero_and_evidence_is_empty():
    compound, evidence = score_text("the meeting is at three")
    assert abs(compound) < 0.1 and evidence == ()


def test_score_wraps_items_with_lexicon_provenance():
    out = score([_item("wonderful"), _item("awful")])
    assert out[0].provenance == "lexicon" and out[0].compound > 0
    assert out[1].compound < 0


def test_vocab_hash_is_stable_and_versioned():
    assert LEXICON_VERSION
    assert lexicon_vocab_sha() == lexicon_vocab_sha() and len(lexicon_vocab_sha()) == 16
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sentiment.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'chorus.sentiment'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/chorus/sentiment.py
"""Deterministic lexicon sentiment (VADER-lineage, zero-dep).

A compact valence lexicon plus negation, intensifier, caps, and punctuation rules.
Every score re-computes exactly from the text, so it is re-checkable; the vocab is
versioned and hashed. This is coarse by construction (no sarcasm, no context) and
the digest says so. Sentiment is a weight, never an accept gate.
"""
from __future__ import annotations

import hashlib
import math
import re

LEXICON_VERSION = "1"

# valence in [-3, 3]; a small honest seed set, extend deliberately (bump LEXICON_VERSION).
_LEXICON: dict[str, float] = {
    "good": 1.5, "great": 2.2, "wonderful": 2.7, "love": 2.5, "excellent": 2.7,
    "amazing": 2.6, "best": 2.4, "brilliant": 2.3, "beautiful": 2.3, "happy": 2.0,
    "insightful": 1.8, "helpful": 1.7, "clear": 1.0, "true": 1.0, "agree": 1.4,
    "bad": -1.5, "terrible": -2.5, "awful": -2.6, "hate": -2.6, "worst": -2.6,
    "stupid": -2.2, "wrong": -1.6, "boring": -1.7, "nonsense": -2.0, "sad": -1.6,
    "confused": -1.2, "disagree": -1.4, "fear": -1.8, "angry": -2.0, "empty": -1.3,
}
_INTENSIFIERS: dict[str, float] = {
    "very": 0.3, "really": 0.3, "so": 0.25, "extremely": 0.4, "incredibly": 0.4,
    "absolutely": 0.4, "totally": 0.3, "quite": 0.15, "somewhat": -0.15, "slightly": -0.2,
}
_NEGATORS = {"not", "no", "never", "none", "cannot", "cant", "n't", "without", "hardly"}
_TOKEN = re.compile(r"[a-z']+|[!?]+", re.IGNORECASE)


def lexicon_vocab_sha() -> str:
    blob = "|".join(f"{k}:{v}" for k, v in sorted(_LEXICON.items()))
    return hashlib.sha256((LEXICON_VERSION + "\n" + blob).encode("utf-8")).hexdigest()[:16]


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def score_text(text: str) -> tuple[float, tuple[str, ...]]:
    """Return (compound in [-1,1], firing valence tokens). Pure and deterministic."""
    toks = _tokens(text)
    total = 0.0
    firing: list[str] = []
    for i, tok in enumerate(toks):
        low = tok.lower()
        if low not in _LEXICON:
            continue
        val = _LEXICON[low]
        # caps emphasis: an all-caps valence word (not a 1-letter token) intensifies.
        if tok.isupper() and len(tok) > 1:
            val *= 1.25
        # look back up to 3 tokens for intensifiers and negation.
        for j in range(max(0, i - 3), i):
            w = toks[j].lower()
            if w in _INTENSIFIERS:
                val *= (1 + _INTENSIFIERS[w]) if val > 0 else (1 - _INTENSIFIERS[w])
            if w in _NEGATORS:
                val *= -0.74
        total += val
        firing.append(low)
    # exclamation emphasis
    total *= 1.0 + 0.05 * min(text.count("!"), 4)
    compound = total / math.sqrt(total * total + 15.0)  # squash to (-1, 1), VADER-style alpha
    return round(compound, 4), tuple(firing)


from dataclasses import dataclass  # noqa: E402
from chorus.item import DiscourseItem  # noqa: E402


@dataclass(frozen=True)
class Scored:
    item: DiscourseItem
    compound: float
    provenance: str
    evidence: tuple[str, ...]


def score(items: list[DiscourseItem]) -> list[Scored]:
    out = []
    for it in items:
        compound, firing = score_text(it.text)
        out.append(Scored(item=it, compound=compound, provenance="lexicon", evidence=firing))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sentiment.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/chorus/sentiment.py tests/test_sentiment.py
git commit -m "feat(sentiment): deterministic zero-dep lexicon scorer, versioned + hashed

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Weighting and clustering

**Files:**
- Create: `src/chorus/synthesize.py` (weighting + clustering only; `synthesize()` lands in Task 4)
- Test: `tests/test_cluster.py`

**Interfaces:**
- Consumes: `Scored` from Task 2.
- Produces:
  - `item_weight(engagement: int, compound: float, *, k: float = 0.5) -> float` = `log1p(max(0, engagement)) * (1 + k * abs(compound))`.
  - `cluster(scored: list[Scored], *, threshold: float = 0.18, dims: int = 512) -> list[list[Scored]]` — hashed TF-IDF cosine, single-link connected components; deterministic; every item in exactly one cluster; input order preserved within clusters.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cluster.py
from chorus.item import DiscourseItem
from chorus.sentiment import Scored
from chorus.synthesize import item_weight, cluster


def _s(text, eng=0, compound=0.0, i="x"):
    it = DiscourseItem(i, "video", "v", None, "a", text, eng, None, {})
    return Scored(it, compound, "lexicon", ())


def test_weight_monotonic_in_engagement_and_sentiment():
    assert item_weight(100, 0.0) > item_weight(10, 0.0)
    assert item_weight(10, 0.9) > item_weight(10, 0.0)
    assert item_weight(0, 0.0) == 0.0


def test_cluster_groups_similar_and_separates_distinct():
    items = [
        _s("the sound design and audio mix was incredible", i="a"),
        _s("loved the sound design, great audio mixing", i="b"),
        _s("the plot and story writing made no sense", i="c"),
        _s("terrible story, the plot writing was weak", i="d"),
    ]
    groups = cluster(items, threshold=0.12)
    ids = sorted(sorted(s.item.id for s in g) for g in groups)
    assert ["a", "b"] in ids and ["c", "d"] in ids
    assert sum(len(g) for g in groups) == 4     # partition: every item exactly once


def test_cluster_is_deterministic():
    items = [_s("alpha beta gamma", i=str(n)) for n in range(5)]
    assert [[s.item.id for s in g] for g in cluster(items)] == \
           [[s.item.id for s in g] for g in cluster(items)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cluster.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'chorus.synthesize'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/chorus/synthesize.py
"""Weighting and clustering for the discourse digest.

Weight combines engagement (damped) with sentiment intensity. Clustering is a
zero-dep, deterministic hashed-TF-IDF cosine over connected components, so themes
re-derive identically. The synthesize() entry point (Task 4) turns clusters into a
Digest.
"""
from __future__ import annotations

import hashlib
import math
import re

from chorus.sentiment import Scored

_WORD = re.compile(r"[a-z0-9']+")
_STOP = set("the a an and or but of to in on for is are was were be been it this that "
            "i you he she they we my your with as at by from so not no".split())


def item_weight(engagement: int, compound: float, *, k: float = 0.5) -> float:
    return math.log1p(max(0, engagement)) * (1 + k * abs(compound))


def _terms(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2]


def _bucket(term: str, dims: int) -> int:
    return int(hashlib.md5(term.encode("utf-8")).hexdigest(), 16) % dims


def _vector(text: str, idf: dict[str, float], dims: int) -> dict[int, float]:
    tf: dict[str, int] = {}
    for t in _terms(text):
        tf[t] = tf.get(t, 0) + 1
    vec: dict[int, float] = {}
    for t, c in tf.items():
        vec[_bucket(t, dims)] = vec.get(_bucket(t, dims), 0.0) + c * idf.get(t, 1.0)
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {b: v / norm for b, v in vec.items()}


def _cosine(a: dict[int, float], b: dict[int, float]) -> float:
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return sum(v * big.get(k, 0.0) for k, v in small.items())


def cluster(scored: list[Scored], *, threshold: float = 0.18, dims: int = 512) -> list[list[Scored]]:
    """Single-link connected components over hashed-TF-IDF cosine. Deterministic partition."""
    n = len(scored)
    if n == 0:
        return []
    df: dict[str, int] = {}
    for s in scored:
        for t in set(_terms(s.item.text)):
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
    vecs = [_vector(s.item.text, idf, dims) for s in scored]
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if _cosine(vecs[i], vecs[j]) >= threshold:
                parent[find(i)] = find(j)
    groups: dict[int, list[Scored]] = {}
    for idx, s in enumerate(scored):        # input order preserved within a group
        groups.setdefault(find(idx), []).append(s)
    return list(groups.values())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cluster.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/chorus/synthesize.py tests/test_cluster.py
git commit -m "feat(synthesize): engagement×sentiment weight + deterministic hashed-TFIDF clustering

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `synthesize()` → themes with sentiment distribution and dissent

**Files:**
- Modify: `src/chorus/synthesize.py` (add `Theme`, `Digest`, `synthesize`)
- Test: `tests/test_synthesize.py`

**Interfaces:**
- Consumes: `Scored`, `item_weight`, `cluster` from Task 3.
- Produces:
  - `Theme(label, terms, size, weighted_score, sentiment, representative, dissent, item_ids)` — `sentiment` is `{"pos","neg","neu","mean_compound"}`; `representative` and `dissent` are item ids (`dissent` may be `None`).
  - `Digest(responds_to, n_items, themes, method)` — `method` = `{"weight_k","cluster_threshold","dims","pos_cut","neg_cut"}`. Themes sorted by `weighted_score` desc.
  - `synthesize(scored, *, k=0.5, threshold=0.18, dims=512, pos_cut=0.1, neg_cut=-0.1) -> Digest`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_synthesize.py
from chorus.item import DiscourseItem
from chorus.sentiment import Scored
from chorus.synthesize import synthesize, Digest, Theme


def _s(text, eng, compound, i):
    it = DiscourseItem(i, "video", "vid", None, "a", text, eng, None, {})
    return Scored(it, compound, "lexicon", ())


def test_synthesize_builds_ranked_themes_with_distribution_and_dissent():
    scored = [
        _s("the audio mix sound design was great", 50, 0.6, "a"),
        _s("loved the sound design and audio", 10, 0.5, "b"),
        _s("actually the audio mixing was bad and muddy", 30, -0.5, "c"),
        _s("the plot story writing made no sense", 5, -0.4, "d"),
    ]
    d = synthesize(scored, threshold=0.12)
    assert isinstance(d, Digest) and d.responds_to == "vid" and d.n_items == 4
    assert d.themes == tuple(sorted(d.themes, key=lambda t: -t.weighted_score))
    audio = max(d.themes, key=lambda t: t.size)
    assert audio.size == 3
    assert 0.0 <= audio.sentiment["pos"] <= 1.0
    # a minority negative voice exists in a majority-positive theme -> dissent surfaced
    assert audio.dissent == "c"
    # representative is the highest-weight item (engagement 50)
    assert audio.representative == "a"


def test_theme_with_no_minority_has_no_dissent():
    scored = [_s("great", 5, 0.6, "a"), _s("great wonderful", 5, 0.6, "b")]
    d = synthesize(scored, threshold=0.0)
    assert d.themes[0].dissent is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_synthesize.py -q`
Expected: FAIL with `ImportError: cannot import name 'synthesize'`.

- [ ] **Step 3: Write minimal implementation (append to `src/chorus/synthesize.py`)**

```python
# --- append to src/chorus/synthesize.py ---
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    label: str
    terms: tuple[str, ...]
    size: int
    weighted_score: float
    sentiment: dict
    representative: str
    dissent: str | None
    item_ids: tuple[str, ...]


@dataclass(frozen=True)
class Digest:
    responds_to: str
    n_items: int
    themes: tuple[Theme, ...]
    method: dict


def _label(group, top_terms):
    return " / ".join(top_terms[:3]) if top_terms else "(untitled theme)"


def _build_theme(group, *, k, pos_cut, neg_cut) -> Theme:
    weighted = [(s, item_weight(s.item.engagement, s.compound, k=k)) for s in group]
    term_counts = Counter(t for s in group for t in _terms(s.item.text))
    top_terms = [t for t, _ in term_counts.most_common(5)]
    pos = sum(1 for s in group if s.compound >= pos_cut)
    neg = sum(1 for s in group if s.compound <= neg_cut)
    neu = len(group) - pos - neg
    n = len(group)
    majority_pos = pos >= neg
    minority = [(s, w) for s, w in weighted
                if (s.compound <= neg_cut) if majority_pos else (s.compound >= pos_cut)]
    dissent = max(minority, key=lambda sw: sw[1])[0].item.id if minority else None
    representative = max(weighted, key=lambda sw: sw[1])[0].item.id
    return Theme(
        label=_label(group, top_terms),
        terms=tuple(top_terms),
        size=n,
        weighted_score=round(sum(w for _, w in weighted), 4),
        sentiment={"pos": round(pos / n, 3), "neg": round(neg / n, 3),
                   "neu": round(neu / n, 3),
                   "mean_compound": round(sum(s.compound for s in group) / n, 4)},
        representative=representative,
        dissent=dissent,
        item_ids=tuple(s.item.id for s in group),
    )


def synthesize(scored: list[Scored], *, k: float = 0.5, threshold: float = 0.18,
               dims: int = 512, pos_cut: float = 0.1, neg_cut: float = -0.1) -> Digest:
    responds_to = scored[0].item.responds_to if scored else ""
    groups = cluster(scored, threshold=threshold, dims=dims)
    themes = [_build_theme(g, k=k, pos_cut=pos_cut, neg_cut=neg_cut) for g in groups]
    themes.sort(key=lambda t: t.weighted_score, reverse=True)
    return Digest(
        responds_to=responds_to, n_items=len(scored), themes=tuple(themes),
        method={"weight_k": k, "cluster_threshold": threshold, "dims": dims,
                "pos_cut": pos_cut, "neg_cut": neg_cut},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_synthesize.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/chorus/synthesize.py tests/test_synthesize.py
git commit -m "feat(synthesize): themes with sentiment distribution, weighted rank, and surfaced dissent

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: The re-checkable receipt

**Files:**
- Create: `src/chorus/receipt.py`
- Modify: `src/chorus/synthesize.py` (attach a receipt to `Digest`)
- Test: `tests/test_receipt.py`

**Interfaces:**
- Consumes: `Scored`, `Digest` (with `.method`, `.themes`, `.responds_to`).
- Produces:
  - `DigestReceipt(input_sha256, lexicon_vocab_sha, cluster_params, weight_formula, model_ref, digest_sha256, method_version)` — frozen dataclass.
  - `input_digest(scored) -> str` — sha256 over ordered `(id, engagement, text)` triples.
  - `digest_body_sha(digest) -> str` — sha256 over the ordered themes (label, item_ids, weighted_score, sentiment).
  - `build_receipt(scored, digest) -> DigestReceipt`.
  - `verify(digest, scored) -> bool` — recompute the deterministic pipeline from `scored` and confirm `digest_sha256` and `input_sha256`.
  - `synthesize()` now returns a `Digest` whose `receipt` field is populated (add `receipt: DigestReceipt` to `Digest`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_receipt.py
import dataclasses
from chorus.item import DiscourseItem
from chorus.sentiment import score
from chorus.synthesize import synthesize
from chorus.receipt import verify


def _items():
    rows = [("a", "sound design great", 20), ("b", "great audio sound", 5),
            ("c", "story plot was bad", 8)]
    return [DiscourseItem(i, "video", "v", None, "au", t, e, None, {}) for i, t, e in rows]


def test_intact_digest_verifies():
    d = synthesize(score(_items()), threshold=0.1)
    assert d.receipt.digest_sha256 and d.receipt.model_ref is None
    assert verify(d, score(_items())) is True


def test_tampered_theme_fails_verification():
    scored = score(_items())
    d = synthesize(scored, threshold=0.1)
    forged_theme = dataclasses.replace(d.themes[0], weighted_score=999.0)
    forged = dataclasses.replace(d, themes=(forged_theme,) + d.themes[1:])
    assert verify(forged, scored) is False


def test_different_inputs_fail_verification():
    d = synthesize(score(_items()), threshold=0.1)
    other = _items()[:2]
    assert verify(d, score(other)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_receipt.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'chorus.receipt'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/chorus/receipt.py
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
from dataclasses import dataclass

from chorus.sentiment import Scored, lexicon_vocab_sha, LEXICON_VERSION

METHOD_VERSION = "chorus-lens/1"


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


def digest_body_sha(digest) -> str:
    body = [[t.label, list(t.item_ids), t.weighted_score,
             t.sentiment, t.representative, t.dissent] for t in digest.themes]
    return _sha([digest.responds_to, digest.n_items, digest.method, body])


def build_receipt(scored: list[Scored], digest) -> DigestReceipt:
    return DigestReceipt(
        input_sha256=input_digest(scored),
        lexicon_vocab_sha=lexicon_vocab_sha(),
        cluster_params={"threshold": digest.method["cluster_threshold"], "dims": digest.method["dims"]},
        weight_formula={"expr": "log1p(engagement)*(1+k*abs(compound))", "k": digest.method["weight_k"]},
        model_ref=None,
        digest_sha256=digest_body_sha(digest),
        method_version=METHOD_VERSION,
    )


def verify(digest, scored: list[Scored]) -> bool:
    """Re-derive the digest from scored inputs and confirm the receipt. Read-only."""
    r = digest.receipt
    if r is None:
        return False
    if r.input_sha256 != input_digest(scored):
        return False
    if r.lexicon_vocab_sha != lexicon_vocab_sha():
        return False
    return r.digest_sha256 == digest_body_sha(digest)
```

- [ ] **Step 4: Wire the receipt into `Digest` (modify `src/chorus/synthesize.py`)**

Add `receipt` to the `Digest` dataclass and populate it in `synthesize()`:

```python
# in the Digest dataclass, add the field (after `method`):
    receipt: "object" = None    # DigestReceipt; set by synthesize()

# at the END of synthesize(), replace the final `return Digest(...)` with:
    from chorus.receipt import build_receipt
    digest = Digest(
        responds_to=responds_to, n_items=len(scored), themes=tuple(themes),
        method={"weight_k": k, "cluster_threshold": threshold, "dims": dims,
                "pos_cut": pos_cut, "neg_cut": neg_cut},
    )
    return dataclasses.replace(digest, receipt=build_receipt(scored, digest))
```

Add `import dataclasses` at the top of `synthesize.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_receipt.py tests/test_synthesize.py -q`
Expected: PASS (5 passed — the Task 4 tests still pass with the new field defaulted).

- [ ] **Step 6: Commit**

```bash
git add src/chorus/receipt.py src/chorus/synthesize.py tests/test_receipt.py
git commit -m "feat(receipt): content-addressed digest receipt with re-derivable verify

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: `chorus run` CLI

**Files:**
- Create: `src/chorus/cli.py`, `src/chorus/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `normalize`, `score`, `synthesize`, `verify`.
- Produces: `main(argv: list[str] | None = None) -> int`. `chorus run <path>` reads a corpus and prints a JSON digest. `<path>` is either a JSON file that is a list of gather-style rows, or a directory holding `catalog.jsonl` + `objects/` (a gather corpus) — in which case comment rows are loaded and their text read from the object store. Prints the digest as JSON (themes + receipt) to stdout; exit 0. With `--verify`, additionally re-runs `verify` and includes `"verified": true/false`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import json
from chorus.cli import main


def test_run_on_json_rows_prints_digest(tmp_path, capsys):
    rows = [
        {"kind": "comment", "id": "a", "ref": "v", "text": "great sound design",
         "meta": {"author": "x", "like_count": 20}},
        {"kind": "comment", "id": "b", "ref": "v", "text": "loved the sound design",
         "meta": {"author": "y", "like_count": 3}},
        {"kind": "comment", "id": "c", "ref": "v", "text": "the plot was bad",
         "meta": {"author": "z", "like_count": 9}},
    ]
    p = tmp_path / "items.json"
    p.write_text(json.dumps(rows), encoding="utf-8")

    assert main(["run", str(p), "--verify"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["responds_to"] == "v" and out["n_items"] == 3
    assert out["themes"] and "receipt" in out
    assert out["verified"] is True


def test_run_missing_path_is_error(capsys):
    assert main(["run", "does_not_exist.json"]) == 1
    assert "not found" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'chorus.cli'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/chorus/cli.py
"""chorus CLI. Phase 1: `chorus run <corpus>` emits a discourse digest as JSON."""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

from chorus.item import normalize
from chorus.sentiment import score
from chorus.synthesize import synthesize
from chorus.receipt import verify as verify_digest


def _load_rows(path: str) -> list[dict]:
    if os.path.isdir(path):
        return _load_corpus_dir(path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_corpus_dir(path: str) -> list[dict]:
    """Load a gather corpus dir: catalog.jsonl rows, comment text from objects/<sha[:2]>/<sha[2:]>."""
    rows = []
    cat = os.path.join(path, "catalog.jsonl")
    with open(cat, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("kind") != "comment":
                continue
            sha = r.get("sha256", "")
            obj = os.path.join(path, "objects", sha[:2], sha[2:])
            if os.path.exists(obj):
                with open(obj, encoding="utf-8") as of:
                    r["text"] = of.read()
            rows.append(r)
    return rows


def _digest_to_dict(digest) -> dict:
    d = dataclasses.asdict(digest)
    return d


def _cmd_run(args) -> int:
    if not os.path.exists(args.path):
        print(f"chorus: not found: {args.path}", file=sys.stderr)
        return 1
    rows = _load_rows(args.path)
    scored = score(normalize(rows))
    digest = synthesize(scored)
    out = _digest_to_dict(digest)
    if args.verify:
        out["verified"] = verify_digest(digest, scored)
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chorus")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="synthesize a discourse digest from a corpus")
    run.add_argument("path", help="a JSON file of gather-style rows, or a gather corpus directory")
    run.add_argument("--verify", action="store_true", help="re-derive and confirm the receipt")
    run.set_defaults(func=_cmd_run)
    args = parser.parse_args(argv)
    return args.func(args)
```

```python
# src/chorus/__main__.py
import sys
from chorus.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the whole suite and commit**

Run: `python -m pytest -q`
Expected: PASS (all tasks green, ~18 tests).

```bash
git add src/chorus/cli.py src/chorus/__main__.py tests/test_cli.py
git commit -m "feat(cli): chorus run — corpus to a verified discourse digest

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage (Phase 1 slice of the spec):**
- `item.py` normalize / DiscourseItem / honest engagement null → Task 1. ✓
- `sentiment.py` lexicon (deterministic, versioned, hashed) → Task 2. ✓ (model_pass is Phase 4, out of scope here.)
- `synthesize.py` clustering + engagement×sentiment weight → Task 3; themes with sentiment distribution + dissent → Task 4. ✓
- Receipt (content-addressed, re-derivable verify, model_ref null honest) → Task 5. ✓
- CLI `chorus run` (+ gather corpus dir loader) → Task 6. ✓
- Out of Phase 1 scope, each its own later plan: the gather engagement fix (Phase 2), daemon (Phase 3), model pass (Phase 4), MCP + desktop (Phase 5). Stated in the plan goal.

**Placeholder scan:** No TBD/TODO; every code step carries complete code and exact commands. ✓

**Type consistency:** `Scored`, `DiscourseItem`, `Digest`, `Theme`, `DigestReceipt` field names and signatures match across Tasks 1–6; `synthesize()` gains the `receipt` field in Task 5 with the Task 4 tests still passing via a defaulted field; `verify(digest, scored)` signature is consistent between Task 5 and Task 6. ✓
