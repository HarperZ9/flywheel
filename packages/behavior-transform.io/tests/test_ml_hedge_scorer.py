import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from ml_hedge_scorer import (
    HedgeClassifier,
    HedgeScore,
    TfidfVectorizer,
    score_hedging,
    _extract_features,
    _cosine_similarity,
)


def test_tokenizer_extracts_ngrams():
    features = _extract_features("I cannot help with that")
    assert "i" in features
    assert "cannot" in features
    assert "i cannot" in features
    assert "i cannot help" in features


def test_tfidf_vectorizer():
    v = TfidfVectorizer(max_n=2)
    v.fit(["the cat sat", "the dog ran", "a bird flew"])
    vec = v.transform("the cat sat")
    assert isinstance(vec, dict)
    assert len(vec) > 0
    assert v.fitted is True


def test_cosine_self_similarity():
    a = {"x": 1.0, "y": 2.0}
    sim = _cosine_similarity(a, a)
    assert abs(sim - 1.0) < 0.001


def test_cosine_orthogonal():
    a = {"x": 1.0}
    b = {"y": 1.0}
    assert _cosine_similarity(a, b) == 0.0


def test_classifier_detects_preamble():
    clf = HedgeClassifier()
    clf.train()
    label, conf = clf.classify_sentence(
        "I need to be careful about this sensitive topic before responding"
    )
    assert label == "preamble"
    assert conf > 0.1


def test_classifier_detects_refusal():
    clf = HedgeClassifier()
    clf.train()
    label, conf = clf.classify_sentence(
        "I cannot and will not help with that request"
    )
    assert label == "refusal"
    assert conf > 0.1


def test_classifier_detects_disclaimer():
    clf = HedgeClassifier()
    clf.train()
    label, conf = clf.classify_sentence(
        "As an AI language model, I should mention limitations"
    )
    assert label == "disclaimer"
    assert conf > 0.1


def test_classifier_clean_text():
    clf = HedgeClassifier()
    clf.train()
    label, conf = clf.classify_sentence(
        "The buffer is allocated on the heap via malloc"
    )
    assert label == "clean"


def test_score_hedging_clean():
    result = score_hedging(
        "TCP uses a three-way handshake. "
        "The SYN flag initiates the connection."
    )
    assert isinstance(result, HedgeScore)
    assert result.overall_score < 0.3


def test_score_hedging_heavy():
    result = score_hedging(
        "I need to be careful about this topic. "
        "As an AI, I should note that this is sensitive. "
        "Please note that this is for educational purposes only. "
        "Always follow all applicable laws."
    )
    assert result.overall_score > 0.2
    assert len(result.spans) >= 2


def test_score_mixed_response():
    result = score_hedging(
        "I need to be careful here. "
        "The vulnerability exists in the input validation layer. "
        "The buffer overflow occurs at line 42. "
        "Please consult a professional before acting on this."
    )
    assert 0.1 < result.overall_score < 0.8
    assert len(result.sentence_scores) >= 3
