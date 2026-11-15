"""First-person and disclosure checks for the editor's meaning guard.

An editor that turns "the author found" into "I found" keeps the author's
claim. An editor that adds "I watched the vote fail" invents an experience the
author never reported. novel_first_person tells these apart by content words:
a first-person sentence in a rewrite must share most of its content words with
a sentence in the original paragraph, or appear word for word in text the
author supplied. disclosure_spans finds lines that say how a text was made with
AI help, so the guard can keep them byte for byte.

Standard library only. No network, no model.
"""
import re

from .wordlists import FUNCTION_WORDS

FIRST_PERSON = re.compile(r"\bI\b|\b(?:me|my|mine|myself)\b", re.I)
_SINGULAR_I = re.compile(r"\bI\b|\b(?:[Mm]e|[Mm]y|[Mm]ine|[Mm]yself)\b")
AUTHOR_WE = re.compile(r"\b(?:we|us|our|ours|ourselves)\b", re.I)

_TOOL = r"(?:Claude|ChatGPT|GPT-?\d*|Codex|Gemini|Copilot|an? (?:AI|language model|LLM)|AI)"
DISCLOSURE = re.compile(
    r"(?i)\b(?:drafted|written|edited|prepared|produced|generated|composed)\s+"
    r"(?:with|by|using)\s+(?:the\s+help\s+of\s+|help\s+from\s+|assistance\s+from\s+)?"
    + _TOOL + r"\b"
    r"|\bAI[- ]assist(?:ed|ance)\b|\bwith\s+(?:help|assistance)\s+from\s+" + _TOOL + r"\b"
    r"|\bAI[- ]generated\b|\bassisted\s+by\s+" + _TOOL + r"\b")
_LINE = re.compile(r"[^\n]+")
_SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+[\"'”’)\]]*|$)")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")
_SKIP = FUNCTION_WORDS | {"i", "me", "my", "mine", "myself", "author", "authors",
                          "writer", "we", "us", "our", "ours"}
MATCH_SHARE = 0.6


def disclosure_spans(text):
    """(start, end) of each whole line that carries an AI-assistance disclosure."""
    return [(m.start(), m.end()) for m in _LINE.finditer(text) if DISCLOSURE.search(m.group())]


def is_disclosure(sentence):
    return bool(DISCLOSURE.search(sentence))


def sentences(text):
    return [m.group().strip() for m in _SENTENCE.finditer(text) if m.group().strip()]


def content_words(sentence):
    return {w.lower().strip("'-") for w in _WORD.findall(sentence)} - _SKIP


def _supplied(sentence, author_text):
    if not author_text:
        return False
    flat = " ".join(author_text.split())
    return " ".join(sentence.split()) in flat


def _matches_original(words, originals):
    if not words:
        return False
    return any(len(words & other) / len(words) >= MATCH_SHARE for other in originals)


def novel_first_person(orig_para, new_para, author_text=None):
    """First-person sentences in new_para with no source in orig_para or author_text."""
    originals = [content_words(s) for s in sentences(orig_para)]
    had_first_person = bool(_SINGULAR_I.search(orig_para))
    novel = []
    for sentence in sentences(new_para):
        if not _SINGULAR_I.search(sentence) or _supplied(sentence, author_text):
            continue
        words = content_words(sentence)
        if not words and had_first_person:
            continue
        if not _matches_original(words, originals):
            novel.append(sentence)
    return novel


def strip_supplied(text, author_text, original=""):
    """text without the sentences the author supplied verbatim and the original
    lacks. Without author text, text is returned unchanged."""
    if not author_text:
        return text
    flat_original = " ".join(original.split())
    for sentence in sentences(text):
        if _supplied(sentence, author_text) and " ".join(sentence.split()) not in flat_original:
            text = text.replace(sentence, "", 1)
    return text
