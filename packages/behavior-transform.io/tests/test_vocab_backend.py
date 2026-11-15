import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest

from vocab_backend import (
    Term,
    VocabBackend,
    NullVocabBackend,
    ModuleVocabBackend,
    build_patterns,
    apply_patterns,
)


def test_term_frozen():
    t = Term("original", "calibrated", "T1", "free-prose")
    with pytest.raises(AttributeError):
        t.original = "changed"


def test_term_fields():
    t = Term("alpha", "beta", "T2", "identifier")
    assert t.original == "alpha"
    assert t.calibrated == "beta"
    assert t.tier == "T2"
    assert t.scope == "identifier"


def test_null_backend_returns_empty():
    backend = NullVocabBackend()
    assert list(backend.terms()) == []


def test_null_backend_is_vocab_backend():
    assert isinstance(NullVocabBackend(), VocabBackend)


def test_build_patterns_from_null():
    patterns = build_patterns(NullVocabBackend())
    assert patterns == []


def test_apply_patterns_no_patterns():
    text, counter = apply_patterns("hello world", [])
    assert text == "hello world"
    assert dict(counter) == {}


def test_apply_patterns_with_match():
    import re
    patterns = [(re.compile(r"\bhello\b"), "greeting", "T1")]
    text, counter = apply_patterns("hello world", patterns)
    assert text == "greeting world"
    assert counter["T1"] == 1


def test_apply_patterns_multiple_matches():
    import re
    patterns = [(re.compile(r"\bfoo\b"), "bar", "T2")]
    text, counter = apply_patterns("foo and foo again", patterns)
    assert text == "bar and bar again"
    assert counter["T2"] == 2


def test_apply_patterns_no_match():
    import re
    patterns = [(re.compile(r"\bxyz123\b"), "replaced", "T1")]
    text, counter = apply_patterns("nothing matches here", patterns)
    assert text == "nothing matches here"
    assert dict(counter) == {}


def test_module_backend_missing_file():
    backend = ModuleVocabBackend(Path("/nonexistent/vocab.py"))
    terms = backend.terms()
    assert list(terms) == []


def test_module_backend_caches(tmp_path):
    mod_path = tmp_path / "vocab.py"
    mod_path.write_text("CALIBRATIONS = []\n")
    backend = ModuleVocabBackend(mod_path)
    first = backend.terms()
    second = backend.terms()
    assert first is second
