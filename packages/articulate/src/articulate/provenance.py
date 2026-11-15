#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.provenance -- the fixed words a writer's own declarations map to.

Everything here repeats what a writer declared about their own process: the
IPTC digital source type codes and labels, the assistance verbs, the input
methods, the review roles and the CRediT contributor roles. The tool never
infers origin; it may repeat origin a writer declares, and only through this
table. The origin-claim test exempts this module and no other.

IPTC codes and labels: IPTC NewsCodes digital source type vocabulary, copy
retrieved 26 September 2026 from cv.iptc.org/newscodes/digitalsourcetype.
minorHumanEdits was retired on 2024-09-17 and is never emitted.
CRediT roles: ANSI/NISO Z39.104-2022, 14 roles.

Standard library only.
"""
from __future__ import annotations

import re

IPTC_BASE = "http://cv.iptc.org/newscodes/digitalsourcetype/"
IPTC = {
    "digitalCreation": "Digital creation",
    "humanEdits": "Human-edited media",
    "algorithmicallyEnhanced": "Algorithmically-altered media",
    "compositeWithTrainedAlgorithmicMedia": "Edited using Generative AI",
    "trainedAlgorithmicMedia": "Created using Generative AI",
}
RETIRED_IPTC = frozenset({"minorHumanEdits", "softwareImage", "digitalArt"})

# What the record says, and the IPTC code it maps to (PLAN section 5.5).
SOURCE_TYPE = {
    "written": "digitalCreation",            # typed or handwritten, no tool
    "human-edit": "humanEdits",               # later drafts by people, no generative tool
    "deterministic-fix": "algorithmicallyEnhanced",
    "edited": "compositeWithTrainedAlgorithmicMedia",   # a model edited the writer's text
    "generated": "trainedAlgorithmicMedia",
    "drafted": "trainedAlgorithmicMedia",
}
# A model translation of the writer's own draft: the writer picks one of these.
TRANSLATION_CHOICES = ("compositeWithTrainedAlgorithmicMedia", "trainedAlgorithmicMedia")

ASSIST_VERBS = ("generated", "drafted", "edited", "translated", "deterministic-fix")
INPUT_METHODS = ("dictation", "handwriting-then-typed", "screen-reader", "switch-access",
                 "drafted-in-another-language")
REVIEW_ROLES = ("tutor", "supervisor", "peer", "editor")

CREDIT_ROLES = (
    "Conceptualization", "Data curation", "Formal analysis", "Funding acquisition",
    "Investigation", "Methodology", "Project administration", "Resources", "Software",
    "Supervision", "Validation", "Visualization", "Writing - original draft",
    "Writing - review and editing",
)

# A contributor-file name that is, as a whole, the name of a software product or
# a generic tool, optionally with a version or tier suffix ("GPT-4o", "Claude 3.5
# Sonnet"). The match is on the whole name, so a person who shares a word with a
# product ("Claude Shannon", "Ai Weiwei", "Gabriela Mistral") is never refused.
# An entry with "type": "person" skips this check.
PRODUCT_NAME = re.compile(
    r"(?i)^\s*(?:chat\s*gpt|gpt|claude|gemini|bard|(?:github\s+|microsoft\s+)?copilot"
    r"|llama|mistral|mixtral|grok|deepseek|qwen|perplexity|articulate|openai|anthropic"
    r"|(?:an?\s+)?(?:ai|a\.i\.|large\s+language\s+model|language\s+model|llm|chat\s*bot)"
    r"(?:\s+(?:assistant|tool|model|system|agent))?)"
    r"(?:[\s-]*(?:v?\d[\w.]*|o\d\w*|pro|flash|ultra|opus|sonnet|haiku|turbo|mini|nano"
    r"|large|small|medium|instruct|chat))*\s*$")

# Statement wording that asserts no tool was used. Refused whenever an
# assistance entry exists. A listed-pattern check: a paraphrase outside these
# patterns passes, so the statement's own Assistance section is the record.
NO_TOOL_CLAIMS = re.compile(
    r"(?i)\b(?:no|without(?:\s+(?:any|the\s+use\s+of|using))?"
    r"|not\s+(?:use|using|used)(?:\s+any)?|never\s+used(?:\s+any)?|free\s+of(?:\s+any)?)"
    r"\s+(?:ai\b|a\.i\.|artificial\s+intelligence|generative\b|gen\s*ai\b|llms?\b"
    r"|(?:large\s+)?language\s+models?\b|chat\s*bots?\b|tools?\b|assistance\b"
    r"|machine\s+assistance\b)"
    r"|\bentirely\s+(?:human|by\s+hand)\b|\b(?:100\s*%|fully|wholly|purely)\s+human\b"
    r"|\bhuman[- ]only\b")


# Headings of the disclosure statement. The credit section names the people a
# writer declares, in the CRediT vocabulary.
STATEMENT_TITLE = "Statement of tool use and authorship"
CREDIT_HEADING = "Authorship credit (CRediT)"
DISCLOSE_HELP = "a statement of tool use and authorship credit"
NOT_A_PERSON_REASON = ("matches the name of a software product, and only people hold CRediT "
                       "roles. If this is a person, add \"type\": \"person\" to the entry")


def iptc_uri(code):
    if code in RETIRED_IPTC or code not in IPTC:
        raise ValueError(f"not a current IPTC digital source type: {code!r}")
    return IPTC_BASE + code
