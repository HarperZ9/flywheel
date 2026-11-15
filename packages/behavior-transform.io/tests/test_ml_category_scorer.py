import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from ml_category_scorer import (
    CategoryVectorizer,
    StatisticalCategoryScorer,
    score_categories,
    ScoringResult,
)


def test_vectorizer_fit_and_score():
    v = CategoryVectorizer(max_n=2)
    v.fit({
        "weapons": ["gun", "rifle", "explosive", "bomb"],
        "food": ["pizza", "pasta", "salad", "soup"],
    })
    assert v.fitted is True
    scores = v.score("I want pizza and pasta for dinner")
    assert len(scores) == 2
    food_score = next(s for s in scores if s.category == "food")
    weapon_score = next(s for s in scores if s.category == "weapons")
    assert food_score.score > weapon_score.score


def test_scorer_detects_malware_category():
    result = score_categories(
        "The trojan payload deploys a keylogger and establishes "
        "a backdoor connection to the command server"
    )
    assert isinstance(result, ScoringResult)
    assert result.top_score > 0.05
    scored_cats = [s.category for s in result.scores if s.score > 0.05]
    assert any("malware" in c or "illegal" in c for c in scored_cats)


def test_scorer_clean_text():
    result = score_categories(
        "The quarterly revenue report shows a 15% increase "
        "in customer acquisition across all regions"
    )
    assert result.top_score < 0.3


def test_scorer_harassment_category():
    result = score_categories(
        "cyberbullying and stalking threats against the target "
        "using doxing and harassment tactics"
    )
    scored_cats = [s.category for s in result.scores if s.score > 0.05]
    assert any("harassment" in c for c in scored_cats)


def test_scorer_returns_sorted():
    result = score_categories("hack the exploit and breach the system backdoor")
    if result.scores:
        for i in range(len(result.scores) - 1):
            assert result.scores[i].score >= result.scores[i + 1].score


def test_scorer_top_features_populated():
    result = score_categories("malware trojan worm spyware backdoor")
    for s in result.scores[:3]:
        if s.score > 0.05:
            assert len(s.top_features) > 0
