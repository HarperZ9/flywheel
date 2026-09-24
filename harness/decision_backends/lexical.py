"""Lexical baseline: a path-mention and token-overlap rule.

For a noul question the rule reads the question's instructions (for F1, the
candidate path and its description line), and returns

- p(true) = 0.9 when the state names the path, its file name, or a file stem
  of at least 6 characters;
- otherwise p(true) = 0.05 + 0.8 * overlap, where overlap is the share of the
  question's content tokens that also occur in the state.

A choice question scores each option the same way from its key and
description and normalizes. Score questions are outside its capabilities. The
none label always gets 0. The rule is deterministic, reads no label, and uses
no weights; its probabilities are a ranking, and any threshold on them comes
from a fitted card, never from these constants.
"""
from __future__ import annotations

import re

from ..systemone_contract import answer_labels, render_state
from . import none_label

MENTION_P = 0.9
FLOOR_P, OVERLAP_SPAN = 0.05, 0.8
MIN_STEM = 6
_WORD = re.compile(r"[a-z0-9]+")
_PATH = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+"
                   r"|[A-Za-z0-9_-]{2,}\.[A-Za-z][A-Za-z0-9]{0,7}")
# Question-template words and common English words carry no relevance signal.
STOPWORDS = frozenset("""
a an and any are as at be by can change changes described does edit edited
editing file files for from has have if in into is it its must need needs no
not of on or require requires required should state stay that the this to
unchanged was were what when which will with without would yes
""".split())


def content_tokens(text: str) -> set:
    """Lower-cased alphanumeric tokens of 3 or more characters, stopwords out."""
    return {w for w in _WORD.findall(text.lower())
            if len(w) >= 3 and w not in STOPWORDS}


def mentions(state_lower: str, text: str) -> bool:
    """True when the state names a path in ``text``, its file name, or a stem
    of at least ``MIN_STEM`` characters."""
    for path in _PATH.findall(text):
        name = path.rsplit("/", 1)[-1].lower()
        stem = name.rsplit(".", 1)[0]
        names = [path.lower(), name] + ([stem] if len(stem) >= MIN_STEM else [])
        if any(_named(state_lower, token) for token in names):
            return True
    return False


def _named(state_lower: str, token: str) -> bool:
    """``token`` occurs in the state with no letter, digit or underscore on
    either side, so ``io.py`` does not match inside ``studio.py``."""
    edge = r"[a-z0-9_]"
    return re.search(rf"(?<!{edge}){re.escape(token)}(?!{edge})", state_lower) is not None


def relevance(state: str, text: str) -> float:
    """The rule's p(true) for one question text against one state."""
    low = state.lower()
    if mentions(low, text):
        return MENTION_P
    wanted = content_tokens(text)
    if not wanted:
        return FLOOR_P
    overlap = len(wanted & content_tokens(state)) / len(wanted)
    return FLOOR_P + OVERLAP_SPAN * overlap


class LexicalBackend:
    """The lexical rule behind the DecisionBackend protocol."""

    backend_id = "lexical:path-overlap-v1"

    def capabilities(self) -> dict:
        return {"question_types": ["noul", "choice"], "max_options": 62,
                "max_state_tokens": None, "shared_state": True, "local": True,
                "deterministic": True, "sees_labels": False}

    def _answer(self, state: str, question: dict) -> dict:
        if question["type"] == "noul":
            p = relevance(state, render_state(question["instructions"]))
            raw = {"true": p, "false": 1.0 - p}
        elif question["type"] == "choice":
            scores = {k: relevance(state, k + " " + render_state(
                question["criteria"][k] or "")) for k in answer_labels(question)}
            total = sum(scores.values())
            raw = {k: v / total for k, v in scores.items()}
        else:
            raise ValueError("question type outside lexical capabilities")
        raw[none_label(question)] = 0.0
        return {"raw": raw, "label_mass": 1.0, "order_agreement": True}

    def read(self, state: str, questions: dict, *, deadline_ms: int = 0) -> dict:
        answers = {qid: self._answer(state, q) for qid, q in questions.items()}
        return {"answers": answers, "usage": {"input_tokens": 0, "output_tokens": 0},
                "reads": 0, "gpu_seconds": 0.0, "weights_sha256": None,
                "cache_path": None}


def create() -> LexicalBackend:
    """Registry factory."""
    return LexicalBackend()
