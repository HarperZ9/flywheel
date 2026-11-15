"""Blind speaker attribution: can a plain classifier tell who said a line?

A complement naive Bayes model over words, word pairs, character trigrams and
punctuation is trained on every other fold of the script and asked to name the
speaker of each held-out line. Priors are uniform, so a character with many
lines is not favoured for that reason. A character whose lines are picked out
well above chance has a voice a model can find; one near chance talks like
everyone else. Standard library only, deterministic.

The score measures surface distinctiveness. It does not prove a voice is good,
and a character can be distinctive for a bad reason (one catchphrase repeated).
"""
import math
from collections import Counter, defaultdict

from .dialogue_lexicon import words

ALPHA = 0.5


def wilson(k, n, z=1.96):
    """Wilson score interval for k successes in n trials, as (low, high)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


def features(text):
    ws = [w.lower() for w in words(text)]
    feats = ["w:" + w for w in ws]
    feats += ["b:%s_%s" % pair for pair in zip(ws, ws[1:])]
    joined = " " + " ".join(ws) + " "
    feats += ["c:" + joined[i:i + 3] for i in range(len(joined) - 2)]
    for mark, tag in (("?", "q"), ("!", "x"), (";", "s"), ("...", "e"), ("…", "e"),
                      (",", "k")):
        feats += ["p:" + tag] * text.count(mark)
    return Counter(feats)


class Model:
    """Complement naive Bayes (Rennie et al., 2003): each speaker is scored by how
    badly the line fits everyone else's counts. Plain naive Bayes sent most lines to
    the speaker with the most text; on the Low Water script the complement form
    raised mean per-speaker accuracy from 0.26 to 0.46 and spread its guesses."""

    def __init__(self, rows):
        self.counts = defaultdict(Counter)
        for speaker, feats in rows:
            self.counts[speaker].update(feats)
        self.totals = {c: sum(v.values()) for c, v in self.counts.items()}
        self.all = Counter()
        for cnt in self.counts.values():
            self.all.update(cnt)
        self.grand = sum(self.all.values())
        self.vocab = len(self.all)

    def posterior(self, feats):
        scores = {}
        for c, cnt in self.counts.items():
            den = math.log(self.grand - self.totals[c] + ALPHA * self.vocab)
            scores[c] = -sum(n * (math.log(self.all.get(f, 0) - cnt.get(f, 0) + ALPHA) - den)
                             for f, n in feats.items())
        top = max(scores.values())
        exp = {c: math.exp(s - top) for c, s in scores.items()}
        z = sum(exp.values())
        return {c: v / z for c, v in exp.items()}


def attribute(lines, min_lines=20, folds=5, block=5):
    """Cross-validated attribution over speakers with at least `min_lines` lines.

    Returns {"speakers": {name: {...}}, "per_line": [{index, rank, p_true, top}], "chance"}.
    `index` points into `lines`. Lines of speakers below the floor are skipped.
    """
    by = Counter(rec["speaker"] for rec in lines)
    keep = sorted(s for s, n in by.items() if n >= min_lines)
    if len(keep) < 2:
        return {"speakers": {}, "per_line": [], "chance": None, "folds": folds,
                "min_lines": min_lines, "note": "fewer than two speakers reach min_lines"}
    idx = [i for i, rec in enumerate(lines) if rec["speaker"] in keep]
    feats = {i: features(lines[i]["text"]) for i in idx}
    # Each speaker's lines are cut into `folds` contiguous runs, in script order, so a
    # held-out line's own scene is mostly held out with it. Round-robin folds let the
    # classifier learn a scene's topic words and overstate distinctiveness.
    seen = Counter()
    fold_of = {}
    for i in idx:
        s = lines[i]["speaker"]
        fold_of[i] = seen[s] * folds // by[s]
        seen[s] += 1
    per_line, post_by = [], {}
    for k in range(folds):
        model = Model([(lines[i]["speaker"], feats[i]) for i in idx if fold_of[i] != k])
        for i in idx:
            if fold_of[i] != k:
                continue
            post = model.posterior(feats[i])
            post_by[i] = post
            order = sorted(post, key=lambda c: (-post[c], c))
            true = lines[i]["speaker"]
            per_line.append({"index": i, "rank": order.index(true) + 1,
                             "p_true": round(post[true], 4), "top": order[0]})
    speakers = {}
    for s in keep:
        rows = [r for r in per_line if lines[r["index"]]["speaker"] == s]
        hit = sum(1 for r in rows if r["rank"] == 1)
        lo, hi = wilson(hit, len(rows))
        speakers[s] = {"lines": len(rows), "correct": hit, "accuracy": round(hit / len(rows), 3),
                       "interval": [round(lo, 3), round(hi, 3)],
                       "block": _blocks(s, rows, post_by, block)}
    return {"speakers": speakers, "per_line": per_line, "chance": round(1 / len(keep), 3),
            "folds": folds, "min_lines": min_lines, "block_size": block}


def _blocks(speaker, rows, post_by, size):
    """Accuracy when the classifier sees `size` held-out lines at once (log
    posteriors summed), closer to how a reader meets a character."""
    rows = sorted(rows, key=lambda r: r["index"])
    hit = n = 0
    for j in range(0, len(rows) - size + 1, size):
        total = Counter()
        for r in rows[j:j + size]:
            for c, p in post_by[r["index"]].items():
                total[c] += math.log(max(p, 1e-300))
        n += 1
        hit += max(total, key=lambda c: (total[c], c)) == speaker
    if n == 0:
        return None
    lo, hi = wilson(hit, n)
    return {"blocks": n, "correct": hit, "accuracy": round(hit / n, 3),
            "interval": [round(lo, 3), round(hi, 3)]}
