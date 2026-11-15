"""Statistical category scorer using TF-IDF n-gram features.

Supplements keyword-based category detection with statistical scoring.
Trained from the existing keyword sets in categories.py, plus synthetic
expansion via n-gram context. Stdlib only.

The scorer produces per-category confidence scores that can be combined
with the keyword detector's severity scores for higher-recall detection.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


_WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def _ngrams(tokens: list[str], n: int) -> list[str]:
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def _extract_features(text: str, max_n: int = 3) -> list[str]:
    tokens = _tokenize(text)
    features = list(tokens)
    for n in range(2, max_n + 1):
        features.extend(_ngrams(tokens, n))
    return features


@dataclass
class CategoryScore:
    """Score for a single category."""
    category: str
    score: float
    top_features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "score": round(self.score, 4),
            "top_features": self.top_features[:5],
        }


@dataclass
class ScoringResult:
    """Result of statistical category scoring."""
    text: str
    scores: list[CategoryScore] = field(default_factory=list)
    top_category: str = "none"
    top_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "top_category": self.top_category,
            "top_score": round(self.top_score, 4),
            "scores": [s.to_dict() for s in self.scores if s.score > 0.05],
        }


class CategoryVectorizer:
    """Per-category TF-IDF model trained from keyword sets."""

    def __init__(self, max_n: int = 3) -> None:
        self._max_n = max_n
        self._idf: dict[str, float] = {}
        self._category_profiles: dict[str, dict[str, float]] = {}
        self._fitted = False

    def fit(self, category_keywords: dict[str, list[str]]) -> None:
        """Build category profiles from keyword sets.

        Each keyword is treated as a mini-document. The category profile
        is the centroid of its keyword vectors.
        """
        all_docs: list[str] = []
        for keywords in category_keywords.values():
            all_docs.extend(keywords)

        n_docs = len(all_docs)
        if n_docs == 0:
            return

        doc_freq: Counter[str] = Counter()
        for doc in all_docs:
            seen = set(_extract_features(doc, self._max_n))
            for f in seen:
                doc_freq[f] += 1

        self._idf = {
            term: math.log((n_docs + 1) / (freq + 1)) + 1
            for term, freq in doc_freq.items()
        }

        for category, keywords in category_keywords.items():
            centroid: dict[str, float] = {}
            for keyword in keywords:
                features = _extract_features(keyword, self._max_n)
                tf: Counter[str] = Counter(features)
                max_tf = max(tf.values()) if tf else 1
                for term, count in tf.items():
                    if term in self._idf:
                        w = (0.5 + 0.5 * count / max_tf) * self._idf[term]
                        centroid[term] = centroid.get(term, 0) + w
            n = len(keywords) or 1
            self._category_profiles[category] = {
                k: v / n for k, v in centroid.items()
            }

        self._fitted = True

    def score(self, text: str) -> list[CategoryScore]:
        """Score text against all category profiles."""
        if not self._fitted:
            return []

        features = _extract_features(text, self._max_n)
        if not features:
            return []

        tf: Counter[str] = Counter(features)
        max_tf = max(tf.values()) if tf else 1
        text_vec: dict[str, float] = {}
        for term, count in tf.items():
            if term in self._idf:
                text_vec[term] = (0.5 + 0.5 * count / max_tf) * self._idf[term]

        if not text_vec:
            return []

        norm_t = math.sqrt(sum(v * v for v in text_vec.values()))
        results = []

        for category, profile in self._category_profiles.items():
            common = set(text_vec.keys()) & set(profile.keys())
            if not common:
                results.append(CategoryScore(category=category, score=0.0))
                continue

            dot = sum(text_vec[k] * profile[k] for k in common)
            norm_p = math.sqrt(sum(v * v for v in profile.values()))
            sim = dot / (norm_t * norm_p) if norm_t and norm_p else 0.0

            top_feats = sorted(common, key=lambda k: text_vec[k] * profile[k], reverse=True)
            results.append(CategoryScore(
                category=category,
                score=sim,
                top_features=top_feats[:5],
            ))

        results.sort(key=lambda r: -r.score)
        return results

    @property
    def fitted(self) -> bool:
        return self._fitted


class StatisticalCategoryScorer:
    """Category scorer that combines keyword and TF-IDF signals."""

    def __init__(self) -> None:
        self._vectorizer = CategoryVectorizer(max_n=3)
        self._trained = False

    def train(self, category_keywords: dict[str, list[str]] | None = None) -> None:
        """Train from category keyword sets."""
        if category_keywords is None:
            from categories import CategoryDetector
            det = CategoryDetector()
            kw = det._build_keywords()
            category_keywords = {
                cat.value: words for cat, words in kw.items()
            }
        self._vectorizer.fit(category_keywords)
        self._trained = True

    def score(self, text: str) -> ScoringResult:
        """Score text against all categories."""
        if not self._trained:
            self.train()

        scores = self._vectorizer.score(text)
        top_cat = "none"
        top_score = 0.0
        if scores and scores[0].score > 0.05:
            top_cat = scores[0].category
            top_score = scores[0].score

        return ScoringResult(
            text=text,
            scores=scores,
            top_category=top_cat,
            top_score=top_score,
        )


_scorer: StatisticalCategoryScorer | None = None


def category_scorer() -> StatisticalCategoryScorer:
    global _scorer
    if _scorer is None:
        _scorer = StatisticalCategoryScorer()
        _scorer.train()
    return _scorer


def score_categories(text: str) -> ScoringResult:
    return category_scorer().score(text)


# --- CLI entry point ----------------------------------------------------------

def main() -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="ml-category-scorer",
        description="Statistical content category scoring using TF-IDF",
    )
    parser.add_argument("text", nargs="?", help="Text to score (or stdin)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    text = args.text or sys.stdin.read()
    result = score_categories(text)

    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(f"Top: {result.top_category} ({result.top_score:.1%})\n")
        for s in result.scores[:5]:
            if s.score > 0.05:
                sys.stdout.write(f"  {s.category}: {s.score:.1%}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
