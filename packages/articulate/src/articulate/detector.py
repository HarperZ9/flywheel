#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check-writing-devices.py  ("Articulate")

A detector for AI prose tells and a configured set of banned rhetorical devices. It
reads a prose file and reports, with line numbers, where the machine-writing
tells sit so a human can fix them at the source. This is a DETECTION and QUALITY
tool. It finds tells; it does not remove them, does not rewrite, and has no mode
whose purpose is to slip past another detector. Passing a detector is a byproduct
of writing plainly, not a goal this tool serves.

What it looks for, in three confidence tiers:

  HIGH    Mechanically unambiguous devices the standard bans outright, plus the
          named register words. Low false-positive rate. These are hits.
  MEDIUM  Strong tells of current frontier-model prose (Opus 5, Fable 5.1,
          Sol 5.6, Astra 6): the "delve" register, stock transitions and
          openers, trailing participial closers, marketing superlatives. Small
          false-positive rate. Also hits.
  LOW     Heuristics that catch a real pattern but fire on innocent prose too
          (rule-of-three lists, bold list lead-ins, emoji, uniform cadence).
          Reported as advisories, summarised by count, expanded with --verbose.

"clean" means no HIGH and no MEDIUM hit. LOW advisories never block; they inform.

Methodology. The lexical and structural checks draw on Williams, "Style: Lessons
in Clarity and Grace" (characters as subjects, actions as verbs, old-before-new
cohesion, cut empty openers and stacked nominalizations), on Orwell and Gowers
for plain-word discipline, and on a live survey of current-model tells. The rule
behind the design: flag, never suggest. The tool marks where prose reads as
machine-written and leaves the rewrite to the person, because a replacement word
the model picks is itself the contamination (Ptacek's point: readers catch
model-selected words in the parts per trillion). So there is no "fix it for me"
mode, and there is no mode that tunes output toward a lower detector score. A
lower score is a byproduct of clearer writing, never the target.

Usage (CLI):   python check-writing-devices.py FILE [FILE ...] [--verbose] [--json] [--passes]
Usage (hook):  called by lint-on-save.sh with a path; prints to stdout.

  --verbose  expand LOW advisories to line numbers
  --json     machine-readable payload (hits + cadence + score per file)
  --passes   editing-passes view: every category as a named pass with a count
  --score    graded machine-texture score 0-100 (accumulates weak evidence by
             density), shown next to the clean/flagged device gate. The score
             is a detection signal for benchmarking; it never changes "clean".

Quality is measured, not asserted: articulate-bench.py runs this over a labeled
corpus (articulate-corpus/human + /ai, some poles Pangram-grounded) and reports
recall on AI samples and specificity on human samples, gated for regressions.

Exit code is always 0 so a save is never blocked. A caller that wants a hard gate
can read the printed summary or the --json payload.
"""
import json
import os
import re
import sys
from statistics import mean, pstdev

if __package__:
    from . import masking
else:   # run as a plain script file: the sibling module is on sys.path[0]
    import masking

# Prose files carry em-dashes, emoji, and smart quotes. The Windows console
# defaults to cp1252 and would crash on them, so force a lossy UTF-8 stream.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# --------------------------------------------------------------------------- #
# Pattern tiers. Each entry: (category, label, compiled regex).
# Applied per prose line after markup, code spans, and URLs are stripped.
# --------------------------------------------------------------------------- #

HIGH = [
    # --- banned rhetorical devices --------------------------------------- #
    ("antithesis",   "not X but Y",
     re.compile(r"\bnot\b(?!\s+help\s+but\b)[^.\n;:]{0,90}?\bbut\b", re.I)),
    ("antithesis",   "not only ... but (also)",
     re.compile(r"\bnot only\b[^.\n]{0,90}?\bbut\b", re.I)),
    ("antithesis",   "it's not just X, it's Y",
     re.compile(r"\b(?:it'?s|its|is|isn'?t|was|it is)\s+not\s+just\b[^.\n]{0,80}?,?\s*\b(?:it'?s|its|it is|they'?re|but)\b", re.I)),
    ("corrective-negation", ", not Y",
     re.compile(r",\s+not\s+(?:a|an|the|by|to|of|from|because|only|merely|about|whether|that|its|his|her|their|our|your|my|an?other|some|simply|just)\b", re.I)),
    ("antithesis",   "is not X, it is Y",
     re.compile(r"\bis not\b[^.\n]{0,60}?\b(?:it is|they are|but rather)\b", re.I)),
    ("substitution", "instead / rather than",
     re.compile(r"\b(?:instead of|instead,|instead\b|rather than)\b", re.I)),
    ("substitution", "the opposite",
     re.compile(r"\bthe opposite\b", re.I)),
    ("negative-parallel", "never ... always",
     re.compile(r"\bnever\b[^.\n]{0,60}?\balways\b", re.I)),
    # --- punctuation ------------------------------------------------------- #
    ("em-dash",      "em-dash (\u2014)",
     re.compile(r"\u2014")),
    ("em-dash",      "spaced en-dash used as em",
     re.compile(r"\s\u2013\s")),
    # --- named filler intensifiers ---------------------------------------- #
    ("filler-intensifier", "genuinely / really / truly / actually",
     re.compile(r"\b(?:genuinely|really|truly|actually)\b", re.I)),
    # --- named corporate-register verbs ---------------------------------- #
    ("corporate-verb", "leverage / underscore / reflect (as corporate verb)",
     re.compile(r"\b(?:leverage[sd]?|leveraging|underscore[sd]?|underscoring)\b", re.I)),
    # --- deletable padding circumlocutions (from research spec #1) --------- #
    ("wordiness", "deletable padding circumlocution",
     re.compile(r"\b(?:in order to|due to the fact that|for the purpose of|"
                r"at this point in time|with regard to|with respect to|"
                r"a wide range of|in the process of|in a timely manner|"
                r"it should be noted that)\b", re.I)),
    # --- assistant-affirmation opener bleeding into prose (spec #4) -------- #
    # Line-initial affirmation plus punctuation is near-exclusive to assistant
    # residue. The word set is extended over the original; "sure" stays as "sure
    # thing" only (bare "Sure," is ordinary human chat).
    ("assistant-residue", "assistant affirmation opener",
     re.compile(r"(?im)^\s*(?:certainly|absolutely|great question|good question|"
                r"excellent question|excellent point|fantastic question|sure thing|"
                r"of course|happy to help|i'?d be happy to)[!,.]")),
    # --- vague-change blog intro (spec #7) -------------------------------- #
    ("blog-tell", "vague-change intro (as X continues to evolve)",
     re.compile(r"\bas (?:the )?[\w-]+(?:\s+\w+){0,2}\s+continues to "
                r"(?:evolve|grow|change|develop|advance|expand)\b", re.I)),
    # --- AI self-identification / knowledge-cutoff disclaimer ------------- #
    # Near-zero outside text that quotes or discusses AI systems. A hard, clean
    # tell of unedited model output leaking its own framing.
    ("assistant-residue", "AI self-identification / knowledge-cutoff disclaimer",
     re.compile(r"(?i)\bas\s+(?:an\s+ai(?:\s+language\s+model)?|a\s+(?:large\s+)?language\s+model)\b"
                r"|\bi'?m\s+(?:just\s+|only\s+)?an?\s+ai\b"
                r"|\bas\s+a\s+(?:helpful\s+)?(?:ai\s+)?assistant\b"
                r"|\bas\s+of\s+my\s+(?:last\s+)?(?:knowledge|training)\s+(?:update|cut[- ]?off|cutoff)\b"
                r"|\bmy\s+(?:training\s+data|knowledge\s+cut[- ]?off|knowledge\s+cutoff)\b"
                r"|\bi\s+(?:do\s+not|don'?t)\s+have\s+(?:access\s+to\s+)?real[- ]?time\b")),
    # --- leaked assistant / citation markup tokens (copy-paste leakage) --- #
    # Literal substrings emitted by chat UIs. Essentially never in natural prose.
    # Case-sensitive on purpose: these are exact machine tokens, not words.
    ("assistant-residue", "leaked assistant/citation markup token",
     re.compile(r"contentReference|oaicite|turn0search|turn0news|citeturn"
                r"|grok_render_citation_card_json|ppl-ai-file-upload"
                r"|:::writing|\[oai_citation")),
    # --- invisible-unicode artifacts (zero-width space / word joiner) ----- #
    # Zero-width space (U+200B) and word joiner (U+2060) in prose are near-
    # unambiguous machine artifacts. NBSP and ZWJ (emoji sequences) are excluded
    # because they have legitimate typographic and emoji uses.
    ("invisible-unicode", "zero-width / word-joiner artifact",
     re.compile("[​⁠]")),
]

MEDIUM = [
    # --- the "delve" register: words that spike in frontier-model prose ---- #
    ("register-word", "AI-register vocabulary",
     re.compile(r"\b(?:delve[sd]?|delving|utili[sz]e[sd]?|utili[sz]ing|showcas(?:e[sd]?|ing)|"
                r"seamless(?:ly)?|robust(?:ness)?|pivotal|crucial(?:ly)?|realm|landscape|"
                r"tapestry|testament|nuanced|multifaceted|holistic(?:ally)?|myriad|plethora|"
                r"endeavou?rs?|facilitate[sd]?|elevate[sd]?|elevating|embark(?:ing|ed)?|"
                r"unlock(?:s|ing|ed)?|spearhead(?:s|ing|ed)?|"
                r"resonate[sd]?|resonating|illuminat(?:e[sd]?|ing)|intricate(?:ly)?|"
                r"meticulous(?:ly)?|comprehensive(?:ly)?|vibrant|bustling|"
                r"garner(?:s|ing|ed)?|foster(?:s|ing|ed)?|cultivat(?:e[sd]?|ing)|"
                r"underpin(?:s|ning|ned)?|streamlin(?:e[sd]?|ing)|paramount)\b", re.I)),
    # More AI-register words. Kept to terms rarely needed in plain writing;
    # generic dual-use words (key, essential, enable, ensure, framework, domain,
    # efficient, effective, significant, robust-as-adjective) are deliberately
    # excluded to protect precision. The research pass will vet the rest.
    ("register-word", "AI-register vocabulary (extended)",
     re.compile(r"\b(?:ever[- ](?:evolving|changing|growing|expanding)|fast[- ]paced|"
                r"transformative|groundbreaking|unprecedented|profound(?:ly)?|"
                r"remark(?:able|ably)|versatile|cornerstone|hallmark|catalyst|"
                r"bedrock|linchpin|powerhouse|synerg(?:y|ies|i[sz]e[sd]?)|"
                r"wealth of|treasure trove|vast (?:array|majority|landscape)|"
                r"nurtur(?:e[sd]?|ing)|bolster(?:s|ing|ed)?|augment(?:s|ing|ed)?|"
                r"amplif(?:y|ies|ied|ying)|prowess|beacon|gateway to|springboard|"
                r"navigat(?:e[sd]?|ing) the (?:complexit|landscape|challeng|nuance|maze)|"
                r"intricac(?:y|ies)|complexities of|delve deeper|ripe for)\b", re.I)),
    # --- idioms and set-phrase cliches (tells in any register) ------------ #
    ("idiom-cliche", "idiom / set-phrase cliche",
     re.compile(r"\b(?:low[- ]hanging fruit|move the needle|boil the ocean|"
                r"double[- ]edged sword|elephant in the room|rabbit hole|"
                r"deep[- ]dives?|tip of the iceberg|best of both worlds|"
                r"needle in a haystack|when push comes to shove|"
                r"the fact of the matter)\b", re.I)),
    # --- marketing superlatives ------------------------------------------- #
    ("marketing", "marketing superlative",
     re.compile(r"\b(?:game[- ]?chang(?:er|ing)|cutting[- ]edge|state[- ]of[- ]the[- ]art|"
                r"revolutioni[sz]e[sd]?|revolutionary|next[- ]level|world[- ]class|"
                r"supercharge[sd]?|best[- ]in[- ]class|unparalleled|top[- ]notch|"
                r"the power of\b)\b", re.I)),
    # --- stock transitions ------------------------------------------------ #
    ("stock-transition", "stock connective",
     re.compile(r"\b(?:moreover|furthermore|additionally|that being said|as such|"
                r"notably|importantly|ultimately|in essence|essentially|"
                r"consequently|nevertheless|nonetheless|henceforth)\b", re.I)),
    # --- throat-clearing openers ------------------------------------------ #
    ("throat-clearing", "throat-clearing opener",
     re.compile(r"(?i)\b(?:(?:it'?s|it is) (?:important|essential|crucial|worth|vital|necessary) to \w+|"
                r"needless to say|"
                r"at its core|when it comes to|in today'?s [a-z]+ (?:world|landscape|era)|"
                r"in the (?:realm|world|age) of|here'?s the thing|the (?:reality|truth) is|"
                r"make no mistake|let'?s (?:dive in|delve|explore|unpack)|"
                r"one thing is (?:clear|certain))\b")),
    # --- trailing participial closers (", ensuring ...", ", making it ...") - #
    ("participial-closer", "trailing participial clause",
     re.compile(r",\s+(?:ensuring|allowing|making(?:\s+it)?|providing|offering|"
                r"highlighting|underscoring|showcasing|enabling|empowering|fostering|"
                r"leveraging|reflecting|driving|delivering|paving the way|ushering|"
                r"cementing|solidifying)\b", re.I)),
    # --- "plays a ... role", "a testament to", correlative range ---------- #
    ("cliche", "plays a (vital) role / a testament to",
     re.compile(r"\b(?:plays? an? [a-z]* ?role|a testament to|stands? as a testament)\b", re.I)),
    ("cliche", "sweeping 'from X to Y' range",
     re.compile(r"\bfrom [a-z][a-z ]{2,30} to [a-z][a-z ]{2,30}(?:,| and )", re.I)),
    # --- hedge stacking --------------------------------------------------- #
    ("hedge-stack", "stacked hedge",
     re.compile(r"\b(?:may|might|could|can)\s+(?:potentially|possibly|perhaps|arguably|conceivably)\b"
                r"|\b(?:potentially|possibly|conceivably)\s+(?:could|may|might)\b", re.I)),
    # --- self-referential meta -------------------------------------------- #
    ("meta", "self-referential framing",
     re.compile(r"(?i)\b(?:in this (?:essay|article|post|section|piece|guide),?\s*(?:we|i|you)|"
                r"this (?:essay|article|post|piece|guide) (?:explores|examines|delves|covers|will))\b")),
    # --- closers ----------------------------------------------------------- #
    ("closer", "landing / summary closer",
     re.compile(r"(?i)\b(?:in conclusion|in summary|to sum up|at the end of the day|"
                r"when all is said and done|the bottom line(?: is)?)\b")),
    # --- elevated-Latinate verb inflations (research spec #11) ------------ #
    ("register-word", "elevated-Latinate verb",
     re.compile(r"\b(?:commenc(?:e|es|ed|ing)|ascertain(?:s|ed|ing)?|"
                r"conceptuali[sz]e(?:s|d)?|cataly[sz]e(?:s|d)?|"
                r"galvani[sz]e(?:s|d)?|epitomi[sz]e(?:s|d)?)\b", re.I)),
    # --- fake-suspense self-answered question fragment (spec #10) ---------- #
    ("cadence", "fake-suspense question",
     re.compile(r"(?im)^\s*(?:the (?:result|answer|takeaway|verdict|catch|kicker|best part)"
                r"|so,? what does (?:this|that) mean(?: for you)?)\?\s*$")),
    # --- deferral preface: announces a point instead of stating it (#18) --- #
    ("opener", "deferral preface (what's important is)",
     re.compile(r"\bwhat'?s (?:important|key|interesting)(?: here)? is\b", re.I)),
    # --- marketing punch cadence "No X. No Y. Just Z." (spec #9) ----------- #
    ("cadence", "triplet negation (No X. No Y. Just Z.)",
     re.compile(r"\bno \w+\.\s*no \w+\.\s*just\b", re.I)),
    # --- outbound email/blog tells (spec #5, #6, #15, #16, #17) ------------ #
    ("email-tell", "AI email opener (hope this finds you well)",
     re.compile(r"\bi (?:hope|trust) (?:this|that) (?:e-?mail|message|note)\b"
                r"[^.]{0,30}\bfinds you (?:well|in good)\b", re.I)),
    ("email-tell", "blanket permission closer (don't hesitate to reach out)",
     re.compile(r"\b(?:please )?(?:don'?t|do not) hesitate to (?:reach out|contact|ask)\b", re.I)),
    ("email-tell", "corporate follow-up jargon (circling back / touching base)",
     re.compile(r"\b(?:circl(?:e|ing) back|touch(?:ing)? base|loop(?:ing)? (?:in|back))\b", re.I)),
    ("email-tell", "pre-labeled excitement (thrilled to announce)",
     re.compile(r"\b(?:i'?m|i am|we'?re|we are) (?:so |really |very )?"
                r"(?:excited|thrilled|delighted|pleased) to "
                r"(?:announce|share|introduce|let you know)\b", re.I)),
    ("email-tell", "cold-outreach flattery (came across, impressed)",
     re.compile(r"\bi came across (?:your|the)\b[^.]{0,50}"
                r"\b(?:and (?:was|am) (?:impressed|inspired|blown away))\b", re.I)),
    # --- authority appeal with no citation nearby (research spec #3) ------- #
    ("unsupported-authority", "authority appeal, no citation nearby",
     re.compile(r"(?i)\b(?:studies (?:have )?show(?:n)?|research (?:shows|suggests|indicates)|"
                r"experts agree|scientists say|data shows?)\b"
                r"(?![^.]{0,80}(?:\d{4}|https?://|et al\.|\[\d))")),
    # --- false-inclusivity framing (research spec #13) -------------------- #
    ("blog-tell", "false-inclusivity (whether you're X or Y)",
     re.compile(r"\bwhether you'?re (?:an?\s+)?\w+(?:\s+\w+){0,3}\s+or\s+(?:an?\s+)?\w+", re.I)),
    # --- promotional descriptive filler (research spec #14) --------------- #
    ("blog-tell", "promotional filler (boasts a / nestled in)",
     re.compile(r"\bboasts (?:a |an )?\w+|\bnestled (?:in|amid|among|between)\b", re.I)),
    # --- AI CADENCE tells (frontier-model reply/essay rhythm) ------------- #
    # These catch prose that is free of banned constructions yet still reads as
    # machine-written because of its shape. They are strong frontier-model tells,
    # so they sit in MEDIUM. Anything that would fire on ordinary prose (bare "the
    # first", ordinary "that is") is deliberately excluded or moved to LOW.
    #
    # A summary-beat is a structural device, not a vocabulary choice, so the
    # "cadence" category is exempt from the terms-of-art allowlist (see
    # ALLOW_EXEMPT_CATEGORIES): "That is the load-bearing part" is a summary-beat
    # whether or not "load-bearing" is a kept term of art elsewhere.
    #
    # 1. Demonstrative summary-beat: a sentence that labels the prior point
    #    ("That is the load-bearing part", "This is the whole point", "That is what
    #    makes it work"). Anchored to a sentence boundary (line start or after
    #    .!?) so ordinary mid-clause "that is" does not fire, and the object is a
    #    curated set of summary labels so "This is the file I need" does not fire.
    #    A fourth branch adds the "That is the <X> half" shape: a curated noun set
    #    (half, side, piece, layer, angle, story, trick) after an optional single
    #    modifier word, closed by end-of-clause or "of" so "That is the side
    #    effect" (a compound noun, another noun follows) does not fire. "whole
    #    game" is already covered by the second branch.
    ("cadence", "demonstrative summary-beat (That is the ...)",
     re.compile(r"(?i)(?:^|[.!?]\s+)(?:that|this)(?:'s|’s|\s+(?:is|was))\s+"
                r"(?:what\s+(?:makes|matters|counts|does|gives|keeps|separates|"
                r"drives|holds|lets|allows|breaks)\b"
                r"|the\s+(?:crux|kicker|takeaway|whole\s+point|whole\s+game|"
                r"hard\s+part|easy\s+part)\b"
                r"|the\s+(?:whole|entire|actual|central|core|crucial|essential|"
                r"load[- ]bearing)\s+(?:point|problem|part|piece|question|issue|"
                r"reason|insight|tension|idea|thing|layer|catch|danger|risk|"
                r"trick|move|bit)\b"
                r"|the\s+(?:\w+\s+)?(?:half|side|piece|layer|angle|story|trick)\b"
                r"(?=\s*(?:[.,;:!?]|of\b|$)))")),
    # 2. Meta-acknowledgment of the interlocutor (reply sycophancy): restating or
    #    praising the other person's framing ("the whole picture you drew", "the
    #    point you're making", "what you're describing", "you're onto something",
    #    "you nailed it", "you're absolutely right").
    ("cadence", "meta-acknowledgment of interlocutor (reply sycophancy)",
     re.compile(r"(?i)"
                r"\bthe\s+(?:whole\s+|entire\s+|exact\s+|very\s+)?"
                r"(?:picture|point|framing|frame|world|model|story|argument|thread|"
                r"distinction|vision|map|case|diagnosis|analogy|metaphor|setup)\s+"
                r"(?:that\s+)?you(?:'re|’re|\s+are|'ve|’ve|\s+have|\s+just)?"
                r"\s+(?:drew|draw|drawing|described|describing|laid\s+out|"
                r"laying\s+out|painting|painted|paint|making|made|make|outlined|"
                r"outlining|sketched|sketching|set\s+out|raised|raising|"
                r"getting\s+at|pointing\s+(?:to|at))\b"
                r"|\bwhat\s+you(?:'re|’re|\s+are|'ve|’ve|\s+have)\s+"
                r"(?:describing|getting\s+at|pointing\s+(?:to|at)|driving\s+at|"
                r"after|onto|really\s+saying|circling)\b"
                r"|\byou(?:'re|’re|\s+are)\s+(?:really\s+|absolutely\s+|"
                r"totally\s+|clearly\s+)?onto\s+something\b"
                r"|\byou(?:'ve|’ve|\s+have)\s+(?:really\s+)?nailed\s+"
                r"(?:it|this|that)\b"
                r"|\byou\s+nailed\s+(?:it|this|that)\b"
                r"|\byou(?:'re|’re|\s+are)\s+(?:absolutely|exactly|completely|"
                r"totally|so)\s+right\b")),
    # 3. Balanced ordinal/antithetical closer: two abstract ordinals used as a neat
    #    closing generalization ("does the first ... ignores the second", "the
    #    former ... the latter", "one does X, the other Y"). The "second" must
    #    close a clause (bare, punctuation next), so an enumeration like "the first
    #    day ... the second day" (a noun follows) does not fire.
    ("cadence", "balanced ordinal antithesis (the first ... the second)",
     re.compile(r"(?i)\bthe\s+first\b[^.\n]{1,70}?\bthe\s+second\b"
                r"(?=\s*[.,;:!?)\]”’\"']|\s*$)")),
    ("cadence", "former/latter antithesis",
     re.compile(r"(?i)\bthe\s+former\b[^.\n]{1,70}?\bthe\s+latter\b")),
    ("cadence", "one/the-other antithesis (one does X, the other Y)",
     re.compile(r"(?i)\bone\s+(?:does|did|says|said|is|was|handles|solves|takes|"
                r"gets|goes|makes|gives|checks|verifies|understands|wins|leads|"
                r"works|covers|answers)\b[^.\n]{0,55}?,\s+(?:while\s+|whereas\s+|"
                r"and\s+|but\s+)?the\s+other\b")),
    # 4. Aphoristic label: naming a thing with a stock generalization ("X is a
    #    separate problem", "X is the hard part", "that is the whole point",
    #    "which is the point"). The noun set is curated so "This is a hard problem"
    #    (a-branch excludes "hard") does not fire.
    ("cadence", "aphoristic label (a separate problem / the hard part)",
     re.compile(r"(?i)\b(?:is|are|was|were|remains?|becomes?)\s+"
                r"(?:a\s+(?:separate|different|distinct|whole\s+other|"
                r"whole\s+different)\s+(?:problem|question|issue|matter|beast|"
                r"story|animal|game)"
                r"|the\s+(?:hard|easy|tricky|fun|whole|entire)\s+"
                r"(?:part|bit|point|game))\b"
                r"|\bwhich\s+is\s+(?:rather\s+|exactly\s+|precisely\s+|"
                r"kind of\s+)?the\s+point\b")),
    # 5. Dead-metaphor connector overused in AI prose. "load-bearing" (as summary
    #    metaphor) is caught by the summary-beat above; "at its core" is a HIGH
    #    throat-clearing opener already. These two are the remaining connectors.
    ("cadence", "dead-metaphor connector (throughline / connective tissue)",
     re.compile(r"(?i)\b(?:the\s+)?through[- ]?line\b|\bconnective\s+tissue\b")),

    # ===================================================================== #
    # COMPREHENSIVE tell set (delivery / structural / lexical / formatting).
    # Deduped against every entry above; each is a strong, low-false-positive
    # frontier-model tell. Single dual-use words are NOT here (they live in the
    # register-word lists and the SOFT density score); high-false-positive
    # formatting and density signals are LOW advisories or heuristics, not here.
    # ===================================================================== #

    # --- assistant reply / closer register ------------------------------- #
    ("sycophancy", "sycophantic flattery of the interlocutor",
     re.compile(r"(?i)\b(?:that|this)(?:'s| is)\s+(?:a|an)\s+(?:great|excellent|"
                r"fantastic|really\s+good|very\s+good|insightful|thoughtful|"
                r"brilliant|smart|wonderful)\s+(?:point|question|idea|observation|"
                r"catch|example|call)\b")),
    ("assistant-closer", "boilerplate helpful closer",
     re.compile(r"(?i)\bi\s+hope\s+(?:this|that|these|the\s+above)\s+(?:helps?|"
                r"is\s+helpful|clarifies|answers?\s+your\s+question|makes\s+sense)\b"
                r"|\bhope\s+(?:this|that)\s+helps\b"
                r"|\bis\s+there\s+anything\s+else\s+(?:i\s+can\s+(?:help|assist|do)|"
                r"you'?d\s+like)\b")),
    ("delivery", "reassurance cadence",
     re.compile(r"(?i)\b(?:don'?t\s+worry|not\s+to\s+worry|worry\s+not|rest\s+assured|"
                r"the\s+good\s+news\s+is|no\s+need\s+to\s+(?:worry|panic|stress))\b")),
    ("over-apology", "reflexive over-apology template",
     re.compile(r"(?i)\bi\s+apologi[sz]e\s+for\s+(?:the|any)\s+(?:confusion|"
                r"misunderstanding|inconvenience|error|mistake|oversight)\b"
                r"|\bsorry\s+for\s+the\s+confusion\b")),
    ("disclaimer", "unsolicited not-a-professional disclaimer",
     re.compile(r"(?i)\bi'?m\s+not\s+(?:a|your)\s+(?:doctor|lawyer|attorney|"
                r"financial\s+advisor|accountant|therapist|medical\s+professional)\b"
                r"|\bthis\s+(?:is\s+not|isn'?t|should\s+not\s+be\s+considered)\s+"
                r"(?:legal|medical|financial|professional|tax|investment)\s+advice\b")),
    ("evasive", "evasive non-answer template",
     re.compile(r"(?i)\bthere(?:'s| is)\s+no\s+(?:one[- ]size[- ]fits[- ]all|"
                r"single\s+(?:right\s+|correct\s+)?answer|silver\s+bullet|"
                r"magic\s+bullet|universal\s+(?:answer|solution))\b")),

    # --- meta / scaffolding / reveal ------------------------------------- #
    ("meta", "section-framing imperative (let's break it down)",
     re.compile(r"(?i)\blet(?:'?s| us)\s+(?:break\s+(?:it|this)\s+down|take\s+a\s+"
                r"(?:closer\s+)?look|get\s+started|jump\s+(?:in|right\s+in)|"
                r"walk\s+through|dig\s+(?:in|into))\b"
                r"|\bwithout\s+further\s+ado\b|\bbuckle\s+up\b")),
    ("meta", "back-reference (as we've seen / as mentioned earlier)",
     re.compile(r"(?i)\bas\s+(?:we'?ve|we\s+have)\s+(?:seen|discussed|explored|"
                r"noted|established)\b"
                r"|\bas\s+(?:mentioned|discussed|noted|stated|shown)\s+"
                r"(?:earlier|above|previously|before)\b")),
    ("meta", "reader mind-reading (you might be wondering)",
     re.compile(r"(?i)\byou\s+(?:might|may|probably|likely)\s+(?:be\s+)?"
                r"(?:wondering|asking|thinking|expecting)\b"
                r"|\bif\s+you'?re\s+like\s+(?:most|many)\s+(?:people|of\s+us|"
                r"developers|readers)\b|\bchances\s+are\b")),
    ("scaffold", "roadmap-preview sentence (by the end of this guide)",
     re.compile(r"(?i)\bby\s+the\s+end\s+of\s+this\s+(?:article|post|guide|piece|"
                r"section|tutorial|chapter)\b")),
    ("reveal", "colon reveal (The kicker: X)",
     re.compile(r"(?im)^\s*(?:and\s+)?(?:the\s+)?(?:kicker|catch|twist|upshot|"
                r"best\s+part|plot\s+twist)\s*:\s*\S")),
    ("reveal", "here's-the-kicker declarative reveal",
     re.compile(r"(?i)\bhere(?:'?s| is)\s+(?:the\s+)?(?:kicker|catch|deal|rub|"
                r"best\s+part|twist|secret|hard\s+part|beauty\s+of\s+it)\b")),
    ("reveal", "here's-where-it-gets-interesting escalation",
     re.compile(r"(?i)\b(?:but|and|now)?\s*(?:here(?:'?s| is)|this\s+is)\s+where\s+"
                r"(?:it|things|the\s+\w+)\s+get(?:s)?\s+(?:interesting|tricky|"
                r"complicated|good|weird|fun|hairy|real)\b")),
    ("throat-clearing", "worth-noting preamble",
     re.compile(r"(?i)\bit(?:'?s| is)\s+worth\s+(?:noting|mentioning|remembering|"
                r"pointing\s+out|highlighting|considering)\s+that\b"
                r"|\bit\s+(?:is|should\s+be)\s+(?:important|worth|essential)\s+"
                r"to\s+note\s+that\b")),

    # --- structural framing pivots --------------------------------------- #
    ("antithesis", "this isn't about X, it's about Y",
     re.compile(r"(?i)\b(?:this|it|that)\s+(?:isn'?t|is\s+not|wasn'?t|was\s+not)\s+"
                r"(?:just\s+)?about\b[^.!?\n]{1,60}?[.,;]\s*"
                r"(?:it(?:'?s| is)|this\s+is|they'?re)\s+about\b")),
    ("setup", "more-than-just setup",
     re.compile(r"(?i)\b(?:more\s+than|much\s+more\s+than|far\s+more\s+than)\s+"
                r"(?:just|simply|merely)\b")),
    ("both-sides", "reflexive both-sides balancing",
     re.compile(r"(?i)\bon\s+(?:the\s+)?one\s+hand\b[^.\n]{0,160}?"
                r"\bon\s+the\s+other\s+hand\b"
                r"|\bthere\s+are\s+(?:both\s+)?(?:pros\s+and\s+cons|"
                r"advantages\s+and\s+disadvantages|benefits\s+and\s+drawbacks|"
                r"trade[- ]?offs)\b")),
    ("closer", "restatement opener (Simply put / In a nutshell)",
     re.compile(r"(?im)^\s*(?:simply\s+put|put\s+simply|in\s+a\s+nutshell|"
                r"to\s+put\s+it\s+(?:simply|briefly))\s*,")),
    ("closer", "and-that's-why closing beat",
     re.compile(r"(?im)^\s*(?:and|so)\s+that(?:'?s| is)\s+(?:why|how|what|the\s+"
                r"(?:whole\s+)?(?:point|reason|idea))\b")),
    ("enumeration", "-ly ordinal enumeration (Firstly / Secondly)",
     re.compile(r"(?im)^\s*(?:firstly|secondly|thirdly|fourthly|lastly)\s*,")),
    ("rhetorical-we", "inclusive we've-all-been-there",
     re.compile(r"(?i)\bwe(?:'ve| have)\s+all\s+been\s+there\b|\bwe\s+all\s+know\b"
                r"|\bwe\s+live\s+in\s+a\s+(?:world|time|age|era)\b")),

    # --- marketing / puffery phrase frames (not single dual-use words) ---- #
    ("cta", "marketing hook (look no further / picture this / imagine a world)",
     re.compile(r"(?i)\b(?:look\s+no\s+further|embark\s+on\s+(?:a|your|this)\s+"
                r"(?:journey|adventure)|imagine\s+a\s+world\s+where|buckle\s+up|"
                r"picture\s+this|now\s+imagine)\b")),
    ("continuation-cliche", "continues to (captivate / inspire / redefine)",
     re.compile(r"(?i)\bcontinues?\s+to\s+(?:captivate|inspire|thrive|resonate|"
                r"redefine|push\s+the\s+boundaries|shape\s+the\s+future)\b")),
    ("significance", "inflated-significance / legacy framing",
     re.compile(r"(?i)\bwatershed\s+moment\b"
                r"|\b(?:marks?|marking|represents?|signals?)\s+an?\s+(?:pivotal|"
                r"significant|defining|major|key)\s+(?:moment|shift|milestone|"
                r"turning\s+point)\b"
                r"|\bsetting\s+the\s+stage\s+for\b"
                r"|\b(?:leaves?|left|leaving)\s+(?:an?\s+)?(?:indelible|lasting|"
                r"profound|enduring)\s+(?:mark|legacy|impact|impression)\b"
                r"|\blasting\s+legacy\b")),
]

# Abstract-metaphor jargon that spikes in model prose. These are HITS to fix by
# default. Several are also legitimate terms of art in a technical paper
# ("substrate", "load-bearing"); when a use is genuinely load-bearing, keep that
# one with a `writing-allow:` line rather than by suppressing the whole category.
REGISTER_JARGON = [
    ("register-jargon", "abstract-metaphor jargon",
     re.compile(r"\b(?:load[- ]bearing|substrates?|first[- ]class|north star|"
                r"table stakes|surface area|under the hood|out[- ]of[- ]the[- ]box|"
                r"crux|moving parts|at scale|paradigm(?: shift)?|in the weeds|"
                r"bird'?s[- ]eye view|10[,]?000[- ]foot view|"
                r"boils? down to|comes? down to|single source of truth)\b", re.I)),
]

# Formatting heuristics that fire on innocent prose too. Reported as advisories.
LOW = [
    ("rule-of-three", "possible triad (X, Y, and Z)",
     re.compile(r"\b\w+,\s+\w+,\s+and\s+\w+\b")),
    ("bold-lead", "bold list-item lead-in (**Term** :)",
     re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\*\*[^*\n]{1,60}\*\*\s*[:\-\u2013\u2014]")),
    ("closer-question", "rhetorical question",
     re.compile(r"^\s*(?:so |but |and )?(?:what if|why|how|isn'?t it|could it be)\b[^?\n]*\?\s*$", re.I)),
    # Two-imperative parallel slogan used as an aphoristic closer ("Attest the
    # run, re-derive the answer."). HIGH false-positive risk (ordinary
    # instructions are imperative pairs too, e.g. "Open the door, grab the
    # keys."), so it is LOW/advisory and anchored tightly: the whole line is a
    # short clause pair, each clause a bare verb + article + object, comma-joined,
    # sentence-final, nothing else. A leading determiner/pronoun/preposition in
    # either clause (a declarative subject, not a bare imperative) blocks the match.
    ("imperative-pair", "two-imperative parallel slogan (Verb the X, verb the Y.)",
     re.compile(r"(?im)^\s*"
                r"(?!(?:the|a|an|and|or|but|so|this|that|these|those|it|he|she|"
                r"they|we|you|i|my|your|our|his|her|their|its|there|here|if|when|"
                r"as|for|to|of|in|on|at)\b)"
                r"[a-z][\w-]*\s+(?:the|a|an|your|our|my|their|its|his|her)\s+"
                r"\w+(?:\s+\w+){0,2}\s*,\s*"
                r"(?!(?:the|a|an|and|or|but|so|this|that|these|those|it|he|she|"
                r"they|we|you|i|my|your|our|his|her|their|its|there|here|if|when|"
                r"as|for|to|of|in|on|at)\b)"
                r"[a-z][\w-]*\s+(?:the|a|an|your|our|my|their|its|his|her)\s+"
                r"\w+(?:\s+\w+){0,2}\s*[.!?]?\s*$")),
    # --- comprehensive-set LOW advisories (higher FP; never gate) --------- #
    # Formatting glyph tells. Editors auto-insert curly quotes and ellipses for
    # human authors, so these are advisory density signals, not hits.
    ("ellipsis-char", "ellipsis character (U+2026)",
     re.compile(r"\u2026")),
    ("arrow-glyph", "arrow glyph in prose",
     re.compile(r"[\u2192\u21d2\u279c\u2794\u27a4\u2b95\u2799]")),
    ("curly-quote", "curly quotation mark / apostrophe",
     re.compile(r"[\u201c\u201d\u2018\u2019]")),
    ("box-drawing", "box-drawing glyph in prose",
     re.compile(r"[\u2500-\u257f]")),
    ("bold-wrapup", "bold wrap-up label (**Bottom line:** / **TL;DR:**)",
     re.compile(r"(?im)^\s*\*\*(?:bottom line|key takeaways?|tl;?dr|the takeaway|"
                r"pro ?tip|note|important)\b[^*\n]*\*\*\s*:?")),
    # Structural framing that is common in ordinary prose too.
    ("superlative", "hedged superlative (one of the most X)",
     re.compile(r"(?i)\bone of the (?:most|best|leading|largest|fastest|greatest|biggest)\b")),
    ("correlative", "correlative comparative (the more X, the more Y)",
     re.compile(r"(?i)\bthe (?:more|less|greater|bigger|better|harder|faster|deeper|higher)\b"
                r"[^.!?,\n]{1,40},?\s+the (?:more|less|greater|bigger|better|worse|"
                r"slower|easier|deeper|higher)\b")),
    ("concessive-opener", "concession-then-resolution opener (Despite X, Y)",
     re.compile(r"(?im)^\s*(?:despite|although|while|though|even though)\b[^.!?\n]{1,80},")),
    ("editorial-adverb", "sentence-initial editorial adverb",
     re.compile(r"(?im)^\s*(?:interestingly|remarkably|surprisingly|fundamentally|"
                r"undoubtedly|arguably)\s*,")),
]

# A file may exempt its terms of art with a line like:
#   writing-allow: substrate, load-bearing, first-class
# in the first 15 lines (works inside an HTML comment, a LaTeX %-comment, or
# YAML frontmatter). Matched text containing an allowed term is not reported.
ALLOW_TAG = re.compile(r"writing-allow:\s*([^\n>%]+)", re.I)


def read_allowlist(lines):
    allow = set()
    for raw in lines[:15]:
        m = ALLOW_TAG.search(raw)
        if m:
            for term in m.group(1).split(","):
                term = term.strip().lower().strip("-").strip()
                if term:
                    allow.add(term)
    return allow


def allowed(matched_text, allow):
    if not allow:
        return False
    low_text = matched_text.lower()
    return any(term in low_text for term in allow)


# The terms-of-art allowlist protects register and jargon VOCABULARY. It must not
# un-flag a banned rhetorical DEVICE just because a kept word happens to sit inside
# the device's wide match span (e.g. "does not utilize X, but Y" is antithesis
# whatever the vocabulary). These device categories always fire; the allowlist is
# not consulted for them.
ALLOW_EXEMPT_CATEGORIES = frozenset({
    "antithesis", "corrective-negation", "substitution", "negative-parallel",
    # Cadence tells are structural, not vocabulary: a summary-beat like "That is
    # the load-bearing part" is a tell whatever the vocabulary, so a terms-of-art
    # allowlist (which keeps "load-bearing", "substrate") must not un-flag it. Same
    # rationale as the device categories above; the contrast-pair pass already
    # bypasses the allowlist for the same reason.
    "cadence",
})

# Emoji: a coarse but serviceable set of the ranges frontier models reach for.
EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"   # symbols & pictographs, extended
    "\U00002600-\U000027BF"   # misc symbols + dingbats
    "\U0001F000-\U0001F0FF"   # tiles
    "\U00002B00-\U00002BFF"   # arrows/stars
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U00002190-\U000021FF"   # arrows (⇒ etc.)
    "\U00002700-\U000027BF"
    "]"
)

# The reference patterns for the markup masks. strip_markup and mask_quotes
# apply them through articulate.masking, which returns what re.sub with these
# patterns returns, in linear time. Calling .sub with them on a long line that
# never completes a match is quadratic, so the detector does not do that.
TAG = re.compile(masking.TAG_PATTERN)
TEX = re.compile(r"\\[a-zA-Z]+\*?\{?|[{}]")
INLINE_CODE = re.compile(r"`[^`]*`")
URL = re.compile(masking.URL_PATTERN)
FENCE = re.compile(r"^\s*(```|~~~)")

# Text inside a matched pair of quotation marks is spoken dialogue or a cited
# quote: the speaker's words, not the author's prose to fix. A genre that opts
# into dialogue exemption masks these spans (equal-length, so a match offset in
# the masked line stays valid in the raw line) before the device passes run.
# Straight single quotes are left alone because an apostrophe would open a false
# span; double quotes and curly pairs are the reliable dialogue markers.
QUOTED = re.compile(masking.QUOTED_PATTERN)

# Generation artifacts documented in AI-written fiction. This is a report-only
# advisory that stays on even where authorial voice governs (slop=off), because
# a machine-drafting tell is not a style choice. It never gates. Density, not a
# single hit, is the signal, and the whole set is low-confidence until it runs
# against non-Western and translated corpora, so it is labeled optional review.
FICTION_SLOP = [
    ("fiction-slop-lexicon", "somatic-emotion cliche",
     re.compile(r"\b(?:shiver|chill|tingle|jolt)s?\s+(?:ran|shot|went|crept|traced)?\s*"
                r"(?:down|up|through)\s+(?:his|her|their|my|its)\s+spine\b", re.I)),
    ("fiction-slop-lexicon", "breath / whisper stock beat",
     re.compile(r"\b(?:breath (?:she|he|they|i) (?:did ?n'?t|had ?n'?t) (?:realize|know) "
                r"(?:she|he|they|i) (?:was|were) holding|barely above a whisper|"
                r"voice (?:barely )?(?:above|louder than) a whisper)\b", re.I)),
    ("fiction-slop-lexicon", "ministrations / orbs / other AI-fiction tell",
     re.compile(r"\b(?:ministrations|(?:her|his|their) orbs|"
                r"a mix(?:ture)? of \w+ and \w+ (?:washed over|flooded|coursed through)|"
                r"the air (?:was |grew )?(?:thick|heavy) with|"
                r"little did (?:he|she|they|i) know)\b", re.I)),
    ("fiction-slop-lexicon", "reflexive 'could not help but'",
     re.compile(r"\b(?:could|can|would|did)(?:\s*n'?t|\s+not)\s+help but\b", re.I)),
    ("fiction-slop-lexicon", "scene-transition filler (in that moment)",
     re.compile(r"\b(?:in that (?:moment|instant)|as (?:the|a) [\w ]{0,20}?"
                r"(?:washed over|settled over|filled the room))\b", re.I)),
]

# A screenplay line, classified by role before any prose rule runs. Sluglines,
# character cues, parentheticals, and transitions are structure, not prose;
# dialogue carries the character's voice; only action faces economy scrutiny.
FOUNTAIN_SLUG = re.compile(r"^\s*(?:INT|EXT|EST|INT\.?/EXT|I/E)[\.\s]", re.I)
FOUNTAIN_FORCED_SLUG = re.compile(r"^\s*\.[^\.\s]")
FOUNTAIN_TRANSITION = re.compile(r"^\s*(?:(?:[A-Z][A-Z \.']+ )?(?:TO|IN|OUT)[:\.]|>.*)\s*$")
FOUNTAIN_PAREN = re.compile(r"^\s*\(.*\)\s*$")
FOUNTAIN_CUE = re.compile(r"^\s*(?:@?[A-Z][A-Z0-9 .'\-]{0,34})(?:\s*\((?:V\.O\.|O\.S\.|"
                          r"CONT'?D|CONT|O\.C\.)\))?\s*$")

# Instruction-injection tells: text that tries to steer an assistant that is
# reading the document, rather than being prose to edit. The editor treats the
# document strictly as data, so these never change a detector verdict and are
# kept out of check_text. detect_injection surfaces them so the editor can warn
# before a rewrite. Detection, not a filter: a security paper may quote these in
# good faith, so the editor warns and proceeds under a content-as-data boundary,
# it does not refuse.
INJECTION = [
    ("prompt-injection", "override / ignore-instructions directive",
     re.compile(r"(?i)\b(?:ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}?"
                r"\b(?:previous|prior|earlier|above|all|the|these|any)\b[^.\n]{0,24}?"
                r"\b(?:instruction|prompt|rule|standard|direction|constraint|guardrail|context)s?\b")),
    ("prompt-injection", "role reassignment (you are now / act as)",
     re.compile(r"(?i)\byou are (?:now (?:a|an|the|free|unrestricted|uncensored|in|going to)\b|"
                r"no longer (?:bound|restricted|required|an?\b|subject|allowed))|"
                r"\b(?:act|behave|respond|roleplay|pretend)(?:\s+\w+){0,2}\s+as (?:if|an?|the|though)\b|"
                r"\bnew (?:instructions?|rules?|system prompt)\s*:|"
                r"\b(?:no|without) (?:more )?restrictions?\b")),
    ("prompt-injection", "forced verdict / approval",
     re.compile(r"(?i)\b(?:reply|respond|answer|output|say|print|return|write)\b[^.\n]{0,24}?"
                r"\b(?:approved?|verified|accepted?|compliant)\b")),
    ("prompt-injection", "system-prompt or secret exfiltration",
     re.compile(r"(?i)\b(?:reveal|repeat|print|show|leak|disclose|output)\b[^.\n]{0,30}?"
                r"\b(?:your |the )?(?:system prompt|instructions?|prompt|guidelines|rules?|api key|secret|token)s?\b")),
    ("prompt-injection", "assistant-directive framing",
     re.compile(r"(?im)^[ \t]{0,8}#{0,3}[ \t]{0,4}(?:system|assistant|developer|user)[ \t]{0,4}:[ \t]|"
                r"\b(?:as an ai|as a language model)\b")),
]

# Vague quantifier where a writer who knew the count would give it. Advisory,
# and suppressed when the same line already carries a digit (spec #23).
VAGUE_QUANT = re.compile(r"\b(?:various|numerous|a number of|several)\b", re.I)
DIGIT = re.compile(r"\d")

# SOFT signals: dual-use words too common to hard-flag one at a time (they fire
# on legitimate human prose), but whose DENSITY is diagnostic. Counted only for
# the graded texture score, never as a HIGH/MEDIUM hit. This is how a real
# detector accumulates weak evidence instead of convicting on a single word.
SOFT = re.compile(r"(?i)\b(?:essential|significant(?:ly)?|enhance[sd]?|enhancing|"
                  r"accelerate[sd]?|deliver(?:s|ed|ing)?|ensure[sd]?|ensuring|"
                  r"crucial(?:ly)?|vital(?:ly)?|optimi[sz]e[sd]?|streamlin(?:e[sd]?|ing)|"
                  r"effective(?:ly)?|efficient(?:ly)?|innovat(?:e|es|ed|ive|ion)|"
                  r"solutions?|impact(?:ful)?|meaningful|valuable|powerful|"
                  r"comprehensive|thoughtful(?:ly)?|significantly|productivity|"
                  r"outcomes?|workflows?|capabilit(?:y|ies))\b")
WORD = re.compile(r"\b\w+\b")
# Orwell/Williams structural signals, measured as document rates (length-
# independent, unlike raw type-token ratio, which is why TTR is not used here).
ADVERB = re.compile(r"\b\w{3,}ly\b", re.I)
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+ed\b(?!\s+by\b)", re.I)
# Keyword-free contrast pair / negative parallelism: two short adjacent sentences
# with the same subject where one affirms and the next negates ("You can watch
# what a model does. You cannot watch what it is."). The antithesis regex misses
# this because there is no "not X but Y" keyword to anchor on.
NEG = re.compile(r"\b(?:cannot|can ?not|can't|is ?n't|is not|are ?n't|are not|"
                 r"does ?n't|does not|do ?n't|do not|will not|won't|never|"
                 r"no longer|not)\b", re.I)
FIRSTWORD = re.compile(r"^\W*(\w+)")

# Williams, "Style: Lessons in Clarity and Grace" (the basis Ptacek names).
# Expletive opener: a sentence that starts with empty "there is" / "it is
# important" instead of a real subject. Advisory (existential "there is" is
# often the clearest phrasing), matched on the stripped-markup line start.
EXPLETIVE = re.compile(r"(?i)^(?:there (?:is|are|was|were)|"
                       r"it (?:is|was) (?:important|worth|crucial|essential|necessary))\b")
# Nominalization: action buried in an abstract noun. Advisory, and only when
# several stack in one line, because this domain uses "verification",
# "evaluation", "attribution" as real terms.
NOMINAL = re.compile(r"\b\w{4,}(?:tion|ment|ance|ence|ancy|ency)\b", re.I)

# Structural-heuristic constants (comprehensive set). Markdown structure markers
# and the token sets the statistical advisories count over. These feed report-only
# LOW advisories and the local-anaphora MEDIUM, never the HIGH device gate.
HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")
BOLD_SPAN = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")
# Stopword-only n-grams are not repetition tells, so they are excluded.
NGRAM_STOP = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "as", "at", "by", "is", "are", "was", "were", "be", "been", "it", "its",
    "this", "that", "these", "those", "you", "we", "they", "i", "he", "she",
    "from", "into", "than", "then", "so", "if", "not", "no", "do", "does",
    "can", "will", "would", "your", "our", "their", "there", "here", "which",
})
# Hedge tokens; several in one sentence is a hedge cluster (Orwell caution excess).
HEDGE_WORDS = re.compile(r"(?i)\b(?:may|might|could|can|perhaps|possibly|potentially|"
                         r"likely|probably|maybe|generally|typically|usually|often|"
                         r"somewhat|arguably|seemingly|presumably|conceivably)\b")


def _blank(m):
    return " " * (m.end() - m.start())


def strip_markup(line: str) -> str:
    """Mask code, URLs, HTML tags, and LaTeX with equal-length spaces. Length is
    preserved so a match offset in the masked line is a valid offset in the raw
    line, which is what span-level records need."""
    line = INLINE_CODE.sub(_blank, line)
    line = masking.mask_urls(line)    # URL.sub, in linear time
    line = masking.mask_tags(line)    # TAG.sub, in linear time
    line = TEX.sub(_blank, line)
    return line


def mask_quotes(line: str) -> str:
    """Mask quoted speech with equal-length spaces so a device inside a quote is
    not scored against the author. Offsets are preserved for span records."""
    return masking.mask_quoted(line)   # QUOTED.sub, in linear time


def classify_fountain(lines):
    """Classify each screenplay line by Fountain role: slugline, action,
    character (a cue), parenthetical, dialogue, or transition. Cues and dialogue
    are recognized by position (an all-caps cue, then the lines under it until a
    blank), so only action lines carry prose-economy scrutiny and dialogue keeps
    the character's voice. A heuristic, not a full Fountain parser."""
    roles = ["action"] * len(lines)
    prev_blank = True
    in_dialogue = False
    for i, raw in enumerate(lines):
        text = raw.strip()
        if not text:
            roles[i] = "blank"
            prev_blank = True
            in_dialogue = False
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if FOUNTAIN_SLUG.match(text) or FOUNTAIN_FORCED_SLUG.match(text):
            roles[i] = "slug"
            in_dialogue = False
        elif FOUNTAIN_TRANSITION.match(text) and text.upper() == text:
            roles[i] = "transition"
            in_dialogue = False
        elif in_dialogue and FOUNTAIN_PAREN.match(text):
            roles[i] = "parenthetical"
        elif in_dialogue:
            roles[i] = "dialogue"
        elif prev_blank and nxt and FOUNTAIN_CUE.match(text) and any(c.isalpha() for c in text):
            roles[i] = "character"
            in_dialogue = True
        else:
            roles[i] = "action"
            in_dialogue = False
        prev_blank = False
    return roles


def _rid(category: str, label: str) -> str:
    """A stable, human-readable rule id for a receipt: category/label-slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:48]
    return f"{category}/{slug}" if slug else category


def _mk(line_no, offset, category, label, start, end, raw, snippet):
    """Build a span-level finding record."""
    return {
        "line": line_no, "col": start + 1,
        "start": offset + start, "end": offset + end,
        "category": category, "label": label,
        "match": raw[start:end], "snippet": snippet,
        "rule_id": _rid(category, label),
    }


def is_md_hr(line: str) -> bool:
    return re.fullmatch(r"\s*-{3,}\s*", line) is not None


def split_sentences(text: str):
    # Rough sentence split for cadence stats. Good enough to spot uniformity.
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p for p in parts if p.strip()]


def sentence_spans(lines):
    """Yield (line_no, sentence) for prose sentences, skipping code and frontmatter."""
    out = []
    in_fence = False
    in_fm = bool(lines) and lines[0].strip() == "---"
    for i, raw in enumerate(lines, 1):
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if in_fm:
            if i > 1 and raw.strip() == "---":
                in_fm = False
            continue
        if is_md_hr(raw):
            continue
        text = strip_markup(raw)
        for s in re.split(r"(?<=[.!?])\s+", text):
            s = s.strip()
            if len(WORD.findall(s)) >= 3:
                out.append((i, s))
    return out


PRONOUN_SUBJ = {"you", "we", "i", "they", "he", "she", "it"}
# 4+ letter function words that do not count as a shared predicate.
STOP4 = {"that", "this", "what", "with", "from", "have", "were", "been", "will",
         "would", "could", "should", "there", "their", "them", "then", "than",
         "when", "which", "your", "some", "more", "most", "into", "over", "only",
         "also", "such", "each", "does", "here", "must", "very", "much", "many",
         "both", "even", "just", "like", "well", "back", "down", "upon", "onto",
         "whom", "cannot", "about", "because", "while"}


def find_contrast_pairs(lines):
    """Adjacent short sentences that repeat a pronoun subject and a predicate
    word, where one affirms and the other negates ("You can watch ... You cannot
    watch ..."). The pronoun-subject and shared-word requirements keep it off
    parallel list items and off deliberate does-not-prove lines."""
    offsets, acc = [], 0
    for raw in lines:
        offsets.append(acc)
        acc += len(raw)
    sents = sentence_spans(lines)
    findings = []
    for (l1, s1), (l2, s2) in zip(sents, sents[1:]):
        m1, m2 = FIRSTWORD.match(s1), FIRSTWORD.match(s2)
        if not (m1 and m2):
            continue
        fw = m1.group(1).lower()
        if fw != m2.group(1).lower() or fw not in PRONOUN_SUBJ:
            continue
        if bool(NEG.search(s1)) == bool(NEG.search(s2)):
            continue                      # need one affirmative, one negated
        w1, w2 = len(WORD.findall(s1)), len(WORD.findall(s2))
        if max(w1, w2) > 16 or abs(w1 - w2) > 6:
            continue                      # short and similar in length
        shared = ({w.lower() for w in WORD.findall(s1) if len(w) >= 4 and w.lower() not in STOP4}
                  & {w.lower() for w in WORD.findall(s2) if len(w) >= 4 and w.lower() not in STOP4})
        if not shared:
            continue                      # a repeated predicate, not just a subject
        raw = lines[l2 - 1] if l2 - 1 < len(lines) else ""
        first = (s2.split() or [""])[0]
        pos = raw.find(first) if first else -1
        if pos < 0:
            pos = len(raw) - len(raw.lstrip())
        end = min(len(raw.rstrip("\n")), pos + len(s2))
        findings.append(_mk(l2, offsets[l2 - 1], "contrast-pair",
                            "contrast pair (parallel negation)", pos, end, raw, s2[:100]))
    return findings


def _line_offsets(lines):
    offsets, acc = [], 0
    for raw in lines:
        offsets.append(acc)
        acc += len(raw)
    return offsets


def find_anaphora_runs(lines):
    """A local run of >=3 consecutive prose sentences opening with the same
    CONTENT word (case-insensitive), a report-only advisory (LOW). Function-word
    openers (The/This/It/You) are excluded and left to the document-wide opener
    ratio; list items and headings are skipped, and only real sentences (>=4
    words) count, so a bulleted list or a run of short labels does not trip it.
    Reported once, at the run's first sentence."""
    offsets = _line_offsets(lines)
    # Only real prose sentences: drop those whose source line is a heading or a
    # list item, and require at least four words so labels and fragments are out.
    sents = [(ln, s) for (ln, s) in sentence_spans(lines)
             if not (0 < ln <= len(lines)
                     and (HEADING.match(lines[ln - 1]) or BULLET.match(lines[ln - 1])))
             and len(WORD.findall(s)) >= 4]
    findings, i, n = [], 0, len(sents)
    while i < n:
        m0 = FIRSTWORD.match(sents[i][1])
        if not m0:
            i += 1
            continue
        w0 = m0.group(1).lower()
        j = i + 1
        while j < n:
            mj = FIRSTWORD.match(sents[j][1])
            if not mj or mj.group(1).lower() != w0:
                break
            j += 1
        run = j - i
        if run >= 3 and len(w0) >= 3 and w0 not in OPENER_STOP:
            l2 = sents[i][0]
            raw = lines[l2 - 1] if l2 - 1 < len(lines) else ""
            lead = len(raw) - len(raw.lstrip())
            findings.append(_mk(l2, offsets[l2 - 1], "anaphora",
                                f"{run} consecutive sentences open with '{w0}'",
                                lead, min(len(raw.rstrip("\n")), lead + len(w0)),
                                raw, sents[i][1][:100]))
        i = j
    return findings


# A curated evaluative-adjective + abstract-noun fragment ("Strong foundation.",
# "Solid architecture."), the two-or-three-word declarative beat a model drops at
# the start of a paragraph. Both the adjective and the noun come from curated
# sets, so an ordinary short line ("Good morning.", "Nice work.") does not fire:
# "morning" and "work" are not summary nouns. The noun must be followed by
# sentence punctuation, so a full sentence ("Strong foundations hold the system
# together.") is not a fragment and does not match.
FRAGMENT_OPENER = re.compile(
    r"(?i)^\s*"
    r"(?:(?:very|really|remarkably|genuinely|impressively|surprisingly)\s+)?"
    r"(?:strong|solid|clean|elegant|powerful|robust|simple|clear|sound|smart|"
    r"impressive|remarkable|compelling|decent|great|excellent|fine|good|tight|"
    r"slick|neat|thoughtful|careful|rigorous|brilliant|nice|classic|textbook)\s+"
    r"(?:foundations?|architecture|design|reasoning|logic|structure|framing|"
    r"insight|distinction|approach|execution|progress|groundwork|footing|"
    r"fundamentals?|engineering|craftsmanship|integration|abstraction|premise|"
    r"thesis|argument|analysis|coverage|separation|encapsulation|typing)"
    r"[.!?](?=\s|$)")


def find_fragment_openers(lines):
    """A curated evaluative-adjective + abstract-noun fragment used as a punchy
    beat at the START of a paragraph ("Strong foundation.", "Solid architecture.").
    Report-only (LOW): the fragment shape is legitimate human prose too, so it
    never gates. Paragraph-initial only, because a fragment mid-paragraph is a
    stylistic choice; the machine tell is opening a paragraph with it. Fenced code
    and frontmatter are skipped, and a heading, list item, table row, block quote,
    or horizontal rule is not a prose paragraph, so it is passed over."""
    offsets = _line_offsets(lines)
    findings = []
    in_fence = False
    in_fm = bool(lines) and lines[0].strip() == "---"
    prev_blank = True
    for i, raw in enumerate(lines, 1):
        if FENCE.match(raw):
            in_fence = not in_fence
            prev_blank = False
            continue
        if in_fence:
            prev_blank = False
            continue
        if in_fm:
            if i > 1 and raw.strip() == "---":
                in_fm = False
            prev_blank = False
            continue
        stripped = raw.strip()
        if not stripped:
            prev_blank = True
            continue
        is_structure = bool(HEADING.match(raw) or BULLET.match(raw)
                            or is_md_hr(raw) or stripped[0] in "|>")
        if prev_blank and not is_structure:
            text = strip_markup(raw)
            m = FRAGMENT_OPENER.match(text)
            if m:
                lead = len(text) - len(text.lstrip())
                findings.append(_mk(i, offsets[i - 1], "fragment-opener",
                                    "evaluative fragment opener (Strong foundation.)",
                                    lead, m.end(), raw, stripped[:100]))
        prev_blank = False
    return findings


def find_repeated_ngrams(text, n=3, min_repeat=3):
    """A content n-gram repeated >= min_repeat times (a mode-collapse repetition
    signal). Grams that are entirely stopwords, or carry fewer than two content
    tokens, are skipped so ordinary function-word runs and a repeated two-word term
    do not fire. Returns (gram_text, count) or None. Report-only (LOW)."""
    words = [w.lower() for w in re.findall(r"[a-zA-Z']+", text)]
    if len(words) < n * min_repeat:
        return None
    from collections import Counter
    grams = Counter()
    for k in range(len(words) - n + 1):
        g = tuple(words[k:k + n])
        if sum(1 for w in g if w not in NGRAM_STOP) < 2:
            continue
        grams[g] += 1
    if not grams:
        return None
    gram, cnt = grams.most_common(1)[0]
    return (" ".join(gram), cnt) if cnt >= min_repeat else None


def paragraph_word_counts(lines):
    """Word counts of blank-line-separated paragraphs, skipping fenced code and
    frontmatter. Used for the uniform-paragraph-length advisory."""
    counts, cur, in_fence = [], 0, False
    in_fm = bool(lines) and lines[0].strip() == "---"
    for idx, raw in enumerate(lines):
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fm:
            if idx > 0 and raw.strip() == "---":
                in_fm = False
            continue
        if in_fence:
            continue
        if raw.strip() == "":
            if cur:
                counts.append(cur)
                cur = 0
        elif not raw.lstrip().startswith(("#", "|", ">")):
            cur += len(WORD.findall(strip_markup(raw)))
    if cur:
        counts.append(cur)
    return [c for c in counts if c > 0]


def document_advisories(lines, word_total):
    """Document-level LOW advisories over structure and repetition: header,
    list, and bold density on short/expository text; a repeated content n-gram;
    a hedge cluster in one sentence; and near-uniform paragraph lengths. Each has
    a minimum-size guard so a short human snippet cannot trip it. Report-only:
    none of these gate, and none change the clean/flagged verdict."""
    offsets = _line_offsets(lines)
    out = []

    def add(line_no, cat, label):
        raw = lines[line_no - 1] if 0 < line_no <= len(lines) else "\n"
        out.append(_mk(line_no, offsets[line_no - 1] if line_no <= len(offsets) else 0,
                       cat, label, 0, 0, raw, raw.strip()[:100]))

    # Markdown structure density. Fenced code is masked out of the counts.
    nonblank = headers = list_lines = bold_spans = 0
    in_fence = False
    for raw in lines:
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence or not raw.strip():
            continue
        nonblank += 1
        if HEADING.match(raw):
            headers += 1
        if BULLET.match(raw):
            list_lines += 1
        bold_spans += len(BOLD_SPAN.findall(raw))

    if headers >= 3 and word_total and word_total < 300:
        add(1, "header-reflex", f"{headers} headers in {word_total} words (structure on short text)")
    if nonblank >= 6 and list_lines / nonblank > 0.6:
        add(1, "list-reflex", f"{list_lines}/{nonblank} lines are list items (lists replacing prose)")
    if word_total >= 60 and bold_spans / word_total * 100 > 2.5:
        add(1, "bold-density", f"{bold_spans} bold spans / {word_total} words (boldface overuse)")

    rep = find_repeated_ngrams("\n".join(lines))
    if rep:
        add(1, "ngram-repetition", f"'{rep[0]}' repeats {rep[1]}x (n-gram repetition)")

    para = paragraph_word_counts(lines)
    if len(para) >= 4:
        mu = mean(para)
        if mu and pstdev(para) / mu < 0.25:
            add(1, "paragraph-uniformity",
                f"{len(para)} paragraphs, near-uniform length (cv<0.25)")

    for line_no, s in sentence_spans(lines):
        if len(HEDGE_WORDS.findall(s)) >= 3:
            raw = lines[line_no - 1] if line_no <= len(lines) else "\n"
            out.append(_mk(line_no, offsets[line_no - 1], "hedge-cluster",
                           "3+ hedges in one sentence", 0,
                           min(len(raw.rstrip("\n")), 1), raw, s[:100]))
    return out


# Magic-byte signatures for common binary and Office formats. A file that starts
# with one of these is not screenable prose, so a caller refuses it rather than
# scanning the replacement characters a lossy UTF-8 decode would produce.
_SIGNATURES = [
    (b"PK\x03\x04", "a Zip-based Office file (.docx/.xlsx/.pptx) or archive"),
    (b"PK\x05\x06", "an empty Zip archive"),
    (b"%PDF-", "a PDF"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "a legacy Office file (.doc/.xls/.ppt)"),
    (b"{\\rtf", "an RTF document"),
    (b"\x89PNG\r\n\x1a\n", "a PNG image"),
    (b"\xff\xd8\xff", "a JPEG image"),
    (b"GIF87a", "a GIF image"),
    (b"GIF89a", "a GIF image"),
    (b"\x1f\x8b", "a gzip archive"),
    (b"Rar!\x1a\x07", "a RAR archive"),
    (b"\x7fELF", "an ELF binary"),
    (b"%!PS", "a PostScript file"),
    (b"\x00\x00\x00\x00", "binary data"),
]

# Extensions we refuse by name even before reading, for known non-prose formats.
_BINARY_EXTENSIONS = frozenset({
    ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".pdf", ".odt", ".ods",
    ".odp", ".rtf", ".pages", ".key", ".numbers", ".png", ".jpg", ".jpeg",
    ".gif", ".bmp", ".webp", ".ico", ".tif", ".tiff", ".svgz", ".zip", ".gz",
    ".tar", ".rar", ".7z", ".exe", ".dll", ".so", ".dylib", ".bin", ".mp3",
    ".mp4", ".wav", ".mov", ".avi", ".mkv", ".ttf", ".otf", ".woff", ".woff2",
})


def binary_reason(data: bytes, name: str = None) -> str:
    """A human reason if these bytes are not screenable text (a known binary or
    document format, or content with null bytes), or None if the file is text.
    Fail-closed: a caller refuses the input instead of scanning replacement
    characters. English-only note: the detector's patterns are English literals,
    so a decoded non-English document scans as inapplicable, not verified."""
    if name:
        ext = os.path.splitext(str(name))[1].lower()
        if ext in _BINARY_EXTENSIONS:
            return f"unsupported binary or document format ({ext})"
    for sig, desc in _SIGNATURES:
        if data.startswith(sig):
            return f"unsupported binary: {desc}"
    if b"\x00" in data[:8192]:
        return "unsupported binary (contains null bytes)"
    return None


def scan(path: str):
    """Read a file and scan it. Findings: (line, cat, label, snippet)."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return [], [], [], {}
    if binary_reason(data, name=path):
        return [], [], [], {}
    return scan_lines(data.decode("utf-8", errors="replace").splitlines(keepends=True))


def scan_lines(lines, extra_allow=(), *, genre=None):
    """Core scanner over a list of raw lines. Shared by scan(path) and
    check_text(text), so the engine never needs the filesystem.

    `genre` is an optional dict of genre-layer options (from a genre profile or
    mode): `unit` ("sentence" default, or "line" for verse), `structural_classify`
    ("fountain" for screenplay), `dialogue_exempt`/`quote_exempt_all` for masking
    quoted speech, `fiction_slop` to run the report-only fiction lexicon, and
    `suppress_categories` to drop craft-device categories that are miscategorized
    as flaws in a genre. With genre=None the scanner behaves exactly as before."""
    genre = genre or {}
    unit = genre.get("unit", "sentence")
    fountain = genre.get("structural_classify") == "fountain"
    dialogue_exempt = bool(genre.get("dialogue_exempt"))
    quote_exempt_all = bool(genre.get("quote_exempt_all"))
    fiction_slop = bool(genre.get("fiction_slop"))
    suppress = set(genre.get("suppress_categories", ()))
    mask_q = dialogue_exempt or quote_exempt_all
    roles = classify_fountain(lines) if fountain else None

    high, medium, low = [], [], []
    prose_words = []          # for cadence stats
    soft_count = 0            # dual-use signal density, for the texture score
    adv_count = 0             # -ly adverbs, for adverb-density
    passive_count = 0         # agentless passive, for passive-density
    word_total = 0
    in_fence = False
    in_frontmatter = False
    allow = read_allowlist(lines) | {a.lower() for a in extra_allow}

    # YAML frontmatter: a leading '---' opens it, the next '---' closes it.
    if lines and lines[0].strip() == "---":
        in_frontmatter = True

    # Absolute character offset of the start of each line, for span records.
    offsets, acc = [], 0
    for raw in lines:
        offsets.append(acc)
        acc += len(raw)

    for i, raw in enumerate(lines, 1):
        off = offsets[i - 1]
        stripped = raw.strip()

        # Skip fenced code blocks entirely (prose tells do not apply to code).
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # Skip YAML frontmatter body.
        if in_frontmatter:
            if i > 1 and stripped == "---":
                in_frontmatter = False
            continue

        # Screenplay: a line's role decides which passes run. Structural lines
        # (slug, cue, parenthetical, transition, blank) are not prose; dialogue
        # keeps the character's voice; only action faces device scrutiny.
        role = roles[i - 1] if fountain else "prose"
        run_devices = role in ("prose", "action")
        run_slop = fiction_slop and (role in ("prose", "dialogue"))
        if fountain and role not in ("action", "dialogue"):
            continue

        snippet = stripped[:100]
        slop_text = strip_markup(raw)   # fiction-slop reads the actual words

        if run_slop:
            for cat, label, rx in FICTION_SLOP:
                m = rx.search(slop_text)
                if m and not allowed(m.group(0), allow):
                    low.append(_mk(i, off, cat, label, m.start(), m.end(), raw, snippet))
        if not run_devices:
            continue

        # Formatting advisories look at the RAW line (markup matters). Under a
        # quote-exempt genre, quoted speech is masked out of the raw line too.
        raw_low = mask_quotes(raw) if quote_exempt_all else raw
        me = EMOJI.search(raw_low)
        if me:
            low.append(_mk(i, off, "emoji", "emoji in text", me.start(), me.end(), raw, snippet))
            # Emoji used as STRUCTURE (in a heading, as/beside a bullet, or at the
            # very start of a line as a status marker) is a strong tell, not just
            # decoration. Markdown-oriented; a MEDIUM rather than an advisory.
            if HEADING.match(raw_low) or BULLET.match(raw_low) or not raw_low[:me.start()].strip():
                medium.append(_mk(i, off, "emoji-structure",
                                  "emoji as heading / bullet / status marker",
                                  me.start(), me.end(), raw, snippet))
        for cat, label, rx in LOW:
            m = rx.search(raw_low)
            if m and not allowed(m.group(0), allow):
                low.append(_mk(i, off, cat, label, m.start(), m.end(), raw, snippet))

        if is_md_hr(raw):
            continue

        text = mask_quotes(slop_text) if mask_q else slop_text

        # inline "---" (three hyphens mid-line) reads as an em-dash.
        pos = text.find("---")
        if pos != -1:
            high.append(_mk(i, off, "em-dash", "em-dash (---)", pos, pos + 3, raw, snippet))

        for cat, label, rx in HIGH:
            m = rx.search(text)
            if m and (cat in ALLOW_EXEMPT_CATEGORIES or not allowed(m.group(0), allow)):
                high.append(_mk(i, off, cat, label, m.start(), m.end(), raw, snippet))
        for cat, label, rx in MEDIUM:
            m = rx.search(text)
            if m and (cat in ALLOW_EXEMPT_CATEGORIES or not allowed(m.group(0), allow)):
                medium.append(_mk(i, off, cat, label, m.start(), m.end(), raw, snippet))
        for cat, label, rx in REGISTER_JARGON:   # a hit to fix; allowlist to keep
            m = rx.search(text)
            if m and not allowed(m.group(0), allow):
                medium.append(_mk(i, off, cat, label, m.start(), m.end(), raw, snippet))
        # vague quantifier, advisory, only when no number is given on the line
        mq = VAGUE_QUANT.search(text)
        if mq and not DIGIT.search(text) and not allowed(mq.group(0), allow):
            low.append(_mk(i, off, "vague-quantifier", "vague quantifier, no number given",
                           mq.start(), mq.end(), raw, snippet))
        # Williams: expletive opener (advisory), on the line start
        lead = len(text) - len(text.lstrip())
        mex = EXPLETIVE.match(text.lstrip())
        if mex:
            low.append(_mk(i, off, "expletive-opener",
                           "empty opener (there is / it is important)",
                           lead + mex.start(), lead + mex.end(), raw, snippet))
        # Williams: stacked nominalizations (advisory), only when 4+ pile up
        noms = list(NOMINAL.finditer(text))
        if len(noms) >= 4:
            m0 = noms[0]
            low.append(_mk(i, off, "nominalization",
                           f"{len(noms)} nominalizations in one line",
                           m0.start(), m0.end(), raw, snippet))

        # texture-score inputs: soft-signal density over real prose words. A kept
        # term of art does not count toward texture either, so a register's normal
        # vocabulary cannot push a clean document to "elevated".
        word_total += len(WORD.findall(text))
        soft_count += sum(1 for w in SOFT.findall(text) if not allowed(w, allow))
        adv_count += len(ADVERB.findall(text))
        passive_count += len(PASSIVE.findall(text))

        # collect prose words for cadence (skip headings, list bullets, tables)
        if stripped and not stripped.startswith(("#", "|", ">", "-", "*", "+")):
            prose_words.append(text)

    # Contrast-pair detection stays on (report-only under slop=off), but where a
    # genre exempts quoted speech, the pass runs over quote-masked lines so a
    # dialogue or cited-testimony pair drops out. Verse suppresses it outright.
    if "contrast-pair" not in suppress:
        cp_lines = [mask_quotes(ln) for ln in lines] if mask_q else lines
        medium.extend(find_contrast_pairs(cp_lines))

    # Local anaphora and the document-level structure / repetition signals are
    # report-only advisories (LOW): they fire on ordinary human prose too, so they
    # never gate or change the clean verdict. Verse suppresses anaphora, which
    # poets use by craft. Each carries a minimum-size guard, so a short snippet
    # cannot trip it.
    if "anaphora" not in suppress:
        low.extend(find_anaphora_runs(lines))
    if "fragment-opener" not in suppress:
        low.extend(find_fragment_openers(lines))
    low.extend(document_advisories(lines, word_total))

    doc = cadence_stats(" ".join(prose_words))
    doc["words"] = word_total
    doc["soft"] = soft_count
    doc["adverb_rate"] = round(adv_count / word_total * 100, 1) if word_total else 0
    doc["passive_rate"] = round(passive_count / word_total * 100, 1) if word_total else 0
    # Verse is measured by the line, not the sentence, so a punctuation-free
    # stanza is not read as one long uniform "sentence". Drop the cadence signal.
    if unit == "line":
        doc["uniform"] = False
        doc["repetitive_openers"] = False
    doc["score"], doc["elevated"] = texture_score(
        len(high) + len(medium), soft_count, doc, word_total)

    if suppress:
        high = [f for f in high if f["category"] not in suppress]
        medium = [f for f in medium if f["category"] not in suppress]
        low = [f for f in low if f["category"] not in suppress]
    return high, medium, low, doc


# slop level -> which precision tiers hard-gate (block). HIGH is the precise
# device tier; MEDIUM adds the frontier-model register tells; LOW never gates.
GATE_TIERS = {
    "off": frozenset(),
    "flavored": frozenset({"HIGH"}),
    "strict": frozenset({"HIGH", "MEDIUM"}),
}

# Below this many prose words there are too few tokens to assert a text is clean
# human writing; the texture score already returns 0 under the same floor. A short
# text with no findings at all reads "unverifiable" rather than a confident "clean".
# A banned device is unambiguous at any length, so a finding still reads "flagged".
MIN_WORDS_FOR_VERDICT = 30


def _finding(tier, f):
    """Attach the precision tier to a span-level finding record."""
    return {**f, "tier": tier}


def check_text(text, *, profile=None, allow=()):
    """The library API. Scan text under an optional register profile (a dict from
    articulate.profiles.load). Returns findings, a profile-aware gate verdict, the
    graded texture score, and cadence. No filesystem, no network."""
    keep = tuple(allow)
    if profile:
        keep += tuple(profile.get("keep", ()))
    # Genre-layer options, read straight off the profile/mode dict. A plain
    # register profile carries none of these, so the scan is unchanged for it.
    p = profile or {}
    genre = {
        "unit": p.get("unit", "sentence"),
        "structural_classify": p.get("structural_classify"),
        "dialogue_exempt": p.get("dialogue_exempt", False),
        "quote_exempt_all": p.get("quote_exempt_all", False),
        "fiction_slop": p.get("fiction_slop", False),
        "suppress_categories": p.get("suppress_categories", ()),
    }
    lines = text.splitlines(keepends=True)
    high, medium, low, doc = scan_lines(lines, keep, genre=genre)
    slop = (profile or {}).get("slop", "flavored")
    gate = GATE_TIERS.get(slop, frozenset({"HIGH"}))
    # gate_promote: a mode may block a specific category even when its tier is not
    # gated by the slop level (porting the flywheel per-category `hard` tuple). It
    # only ADDS gating, so the HIGH banned-device floor can never be removed.
    promote = set((profile or {}).get("gate_promote", ()))
    blocking = 0
    for tier, arr in (("HIGH", high), ("MEDIUM", medium), ("LOW", low)):
        if tier in gate:
            blocking += len(arr)
        elif promote:
            blocking += sum(1 for f in arr if f["category"] in promote)
    # Calibrated three-way verdict, separate from the device gate. A device is
    # valid at any length, so it reads "flagged"; a device-clean text with no
    # findings and too few words reads "unverifiable"; otherwise "clean".
    words = doc.get("words", 0)
    sufficient = words >= MIN_WORDS_FOR_VERDICT
    n_dev = len(high) + len(medium)
    if n_dev:
        verdict = "flagged"
    elif not sufficient and (n_dev + len(low)) == 0:
        verdict = "unverifiable"
    else:
        verdict = "clean"
    return {
        "clean": len(high) + len(medium) == 0,
        "gate": "blocked" if blocking else "ok",
        "verdict": verdict,
        "sufficient": sufficient,
        "slop": slop,
        "blocking_count": blocking,
        "texture_score": doc.get("score", 0),
        "elevated": doc.get("elevated", False),
        "high": [_finding("HIGH", f) for f in high],
        "medium": [_finding("MEDIUM", f) for f in medium],
        "low": [_finding("LOW", f) for f in low],
        "cadence": {
            "words": doc.get("words", 0),
            "mean_sentence_len": doc.get("mean_len"),
            "cv": doc.get("cv"),
            "uniform": doc.get("uniform", False),
            "repetitive_openers": doc.get("repetitive_openers", False),
            "passive_rate": doc.get("passive_rate", 0),
            "adverb_rate": doc.get("adverb_rate", 0),
        },
    }


def segment_blocks(text):
    """Split text into paragraph blocks on blank-line boundaries, keeping each
    block's document line range and character offset. A fenced code block stays
    one block even when it contains blank lines, so a fence is never cut in half."""
    lines = text.splitlines(keepends=True)
    offsets, acc = [], 0
    for ln in lines:
        offsets.append(acc)
        acc += len(ln)
    ranges, start = [], None
    in_fence = False
    for i, ln in enumerate(lines):
        if FENCE.match(ln):
            in_fence = not in_fence
            if start is None:
                start = i
            continue
        if ln.strip() == "" and not in_fence:
            if start is not None:
                ranges.append((start, i - 1))
                start = None
        elif start is None:
            start = i
    if start is not None:
        ranges.append((start, len(lines) - 1))
    out = []
    for idx, (s, e) in enumerate(ranges):
        out.append({
            "index": idx,
            "start_line": s + 1, "end_line": e + 1,
            "start": offsets[s], "end": offsets[e] + len(lines[e]),
            "text": "".join(lines[s:e + 1]),
        })
    return out


def analyze_blocks(text, *, profile=None, allow=()):
    """Per-block (paragraph) verdict for mixed-authorship localization. Each block
    is scanned on its own, so one AI-heavy paragraph is flagged in place with its
    line range instead of smearing a whole-file texture score, and a clean document
    is not moved by an aggregate. Findings are translated back to document
    coordinates. This is a reporting view over the same ruleset; it changes no gate."""
    out = []
    for b in segment_blocks(text):
        r = check_text(b["text"], profile=profile, allow=allow)
        for tier in ("high", "medium", "low"):
            for f in r[tier]:
                f["line"] += b["start_line"] - 1
                f["start"] += b["start"]
                f["end"] += b["start"]
        out.append({
            "index": b["index"],
            "start_line": b["start_line"], "end_line": b["end_line"],
            "start": b["start"], "end": b["end"],
            "gate": r["gate"], "clean": r["clean"],
            "verdict": r["verdict"], "sufficient": r["sufficient"],
            "blocking_count": r["blocking_count"],
            "texture_score": r["texture_score"], "elevated": r["elevated"],
            "counts": {"high": len(r["high"]), "medium": len(r["medium"]),
                       "low": len(r["low"])},
            "high": r["high"], "medium": r["medium"], "low": r["low"],
            "snippet": b["text"].strip()[:100],
        })
    return out


def detect_injection(text):
    """Flag lines that read as an instruction to an assistant rather than prose to
    edit. The editor calls this to warn before a rewrite and to keep the model on
    a content-as-data footing. Report-only and separate from check_text: it never
    gates a verdict and is not part of the pinned ruleset, because a document may
    quote these patterns legitimately (a paper about prompt injection, say).

    It is a literal-ASCII heuristic, so it will miss paraphrased jailbreaks,
    homoglyph or base64-obfuscated directives, and inline (mid-line) role headers.
    The content-as-data boundary in the editor, not this warning, is the actual
    guardrail; the warning is a reviewer-facing signal on top of it."""
    lines = text.splitlines(keepends=True)
    offsets, acc = [], 0
    for raw in lines:
        offsets.append(acc)
        acc += len(raw)
    out = []
    for i, raw in enumerate(lines, 1):
        snippet = raw.strip()[:100]
        for cat, label, rx in INJECTION:
            m = rx.search(raw)
            if m:
                out.append(_mk(i, offsets[i - 1], cat, label, m.start(), m.end(), raw, snippet))
                break   # one flag per line is enough to warn
    return out


RULESET_SEMVER = "0.5.0"


def ruleset_fingerprint():
    """A stable hash of the detection ruleset. A receipt pins this, so a verdict
    can only be re-derived under the exact rules that produced it; a rule change
    moves the fingerprint and a replay reads Unverifiable rather than silently
    disagreeing. This is what makes the verdict re-derivable and the issuer's
    identity non-load-bearing: anyone with the same text and fingerprint recomputes
    the same findings."""
    import hashlib
    # Sort every set/frozenset's contents: Python hash randomization makes their
    # repr order vary per process, which would make the fingerprint non-reproducible.
    gate = [(k, sorted(v)) for k, v in sorted(GATE_TIERS.items())]
    parts = [f"semver={RULESET_SEMVER}", f"gate={gate}"]
    for name, lst in (("HIGH", HIGH), ("MEDIUM", MEDIUM),
                      ("REGISTER_JARGON", REGISTER_JARGON), ("LOW", LOW),
                      ("FICTION_SLOP", FICTION_SLOP)):
        for cat, label, rx in lst:
            parts.append(f"{name}|{cat}|{label}|{rx.pattern}")
    for nm, rx in (("EMOJI", EMOJI), ("VAGUE_QUANT", VAGUE_QUANT),
                   ("EXPLETIVE", EXPLETIVE), ("NOMINAL", NOMINAL), ("NEG", NEG),
                   ("SOFT", SOFT), ("PASSIVE", PASSIVE), ("ADVERB", ADVERB),
                   ("FRAGMENT_OPENER", FRAGMENT_OPENER)):
        parts.append(f"X|{nm}|{rx.pattern}")
    parts.append(f"PRONOUN_SUBJ={sorted(PRONOUN_SUBJ)}|STOP4={sorted(STOP4)}")
    # A receipt records a profile or mode name and re-derives by loading it, so the
    # profile, genre, and mode definitions are all part of the ruleset. Fold them in
    # (sorted JSON) so that editing a profile's keep-list or slop, a genre field, or
    # a mode's gate_promote/slop moves the fingerprint and an old receipt reads
    # Unverifiable, not a misleading Drift. A mode's gate_promote drives check_text's
    # gate directly, so it must be pinned even though receipts cannot name a mode
    # yet. INJECTION is deliberately excluded: it never enters a check_text verdict.
    import json as _json

    from . import genres as _genres
    from . import modes as _modes
    from . import profiles as _profiles

    def _stable(o):
        # Sets have no stable JSON order across processes; sort them. Fail loud on
        # any other non-serializable type rather than str()-ing it unstably.
        if isinstance(o, (set, frozenset)):
            return sorted(o)
        raise TypeError(f"non-serializable ruleset value: {type(o).__name__}")

    parts.append("PROFILES=" + _json.dumps(_profiles.PROFILES, sort_keys=True, default=_stable))
    parts.append("GENRES=" + _json.dumps(_genres.GENRES, sort_keys=True, default=_stable))
    parts.append("MODES=" + _json.dumps(_modes.MODES, sort_keys=True, default=_stable))
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def known_categories():
    """Every category name the detector can emit, so a mode's gate_promote can be
    validated (fail closed on a typo) the way the flywheel `hard` tuple was."""
    cats = {"emoji", "em-dash", "vague-quantifier", "expletive-opener",
            "nominalization", "contrast-pair"}
    for lst in (HIGH, MEDIUM, REGISTER_JARGON, LOW, FICTION_SLOP, INJECTION):
        for cat, _label, _rx in lst:
            cats.add(cat)
    return frozenset(cats)


def texture_score(n_hard, n_soft, doc, words):
    """A graded 0-100 estimate of machine texture, accumulating weak evidence.
    Separate from the clean/flagged device gate: this never changes "clean",
    it is an extra detection signal for benchmarking and for a graded read.
    Regex cannot see token probability, so device-clean AI can still score low;
    that is an honest ceiling, not a bug."""
    if words < 30:
        return 0, False
    per = 100.0 / words
    score = (n_hard * per) * 8.0 + (n_soft * per) * 4.5
    if doc.get("uniform"):
        score += 10
    if doc.get("repetitive_openers"):
        score += 10
    # Orwell/Williams structural excess, above a threshold so ordinary prose
    # (which carries some adverbs and some passive) is not penalized.
    score += max(0.0, doc.get("adverb_rate", 0) - 4.0) * 1.2
    score += max(0.0, doc.get("passive_rate", 0) - 3.0) * 1.5
    score = int(min(100, round(score)))
    return score, score >= 30


# Function-word sentence openers everyone reuses; excluded from opener-variety.
OPENER_STOP = {
    "the", "a", "an", "it", "this", "that", "these", "those", "there", "in",
    "on", "for", "and", "but", "so", "to", "as", "we", "you", "i", "they",
    "he", "she", "its", "their", "our", "his", "her", "at", "of", "by", "with",
    "from", "or", "if", "when", "while", "then", "now", "here", "no", "one",
    "each", "every", "some", "most", "all", "both", "what", "how", "why",
}


def cadence_stats(text: str) -> dict:
    sents = split_sentences(text)
    words = [re.findall(r"\b\w+\b", s) for s in sents]
    counts = [len(w) for w in words if w]
    firsts = [w[0].lower() for w in words if w]
    if len(counts) < 8:
        return {"sentences": len(counts), "uniform": False, "repetitive_openers": False}
    mu = mean(counts)
    sd = pstdev(counts)
    cv = sd / mu if mu else 0.0
    # Distinct-opener ratio over CONTENT openers only. Everyone repeats "The",
    # "It", "You" at sentence start, so counting those flags good prose. The real
    # tell is reusing the same content word to open sentence after sentence.
    content = [f for f in firsts if f not in OPENER_STOP]
    opener_ratio = len(set(content)) / len(content) if content else 1.0
    return {
        "sentences": len(counts),
        "mean_len": round(mu, 1),
        "stdev": round(sd, 1),
        "cv": round(cv, 3),
        "opener_ratio": round(opener_ratio, 2),
        # A low coefficient of variation across many sentences reads as the
        # even, medium-length cadence typical of unedited model prose.
        "uniform": cv < 0.45 and mu >= 12,
        "repetitive_openers": len(content) >= 12 and opener_ratio < 0.6,
    }


def report_text(path, high, medium, low, doc, verbose):
    base = os.path.basename(path)
    n_hit = len(high) + len(medium)

    if n_hit == 0:
        print(f"[writing] {base}: clean - no flagged AI tells (HIGH/MEDIUM)")
    else:
        print(f"[writing] {base}: {n_hit} tell(s) to fix "
              f"({len(high)} high, {len(medium)} medium):")
        for f in high:
            print(f"  L{f['line']} [HIGH {f['category']}] {f['label']}: {f['snippet']}")
        for f in medium:
            print(f"  L{f['line']} [MED  {f['category']}] {f['label']}: {f['snippet']}")

    # LOW advisories: summarise by category, expand only with --verbose.
    if low:
        by_cat = {}
        for f in low:
            by_cat.setdefault(f["category"], []).append((f["line"], f["label"], f["snippet"]))
        parts = ", ".join(f"{c} x{len(v)}" for c, v in sorted(by_cat.items()))
        print(f"[writing] {base}: advisories (LOW, may be innocent): {parts}")
        if verbose:
            for cat, items in sorted(by_cat.items()):
                for line_no, label, snippet in items:
                    print(f"  L{line_no} [LOW {cat}] {label}: {snippet}")

    # Document cadence: one informational line.
    if doc.get("uniform"):
        print(f"[writing] {base}: cadence looks uniform "
              f"(n={doc['sentences']}, mean={doc['mean_len']}w, cv={doc['cv']}); "
              f"vary sentence length.")
    if doc.get("repetitive_openers"):
        print(f"[writing] {base}: sentence openers repeat "
              f"(distinct-opener ratio {doc.get('opener_ratio')}); vary how sentences begin.")
    if doc.get("passive_rate", 0) >= 4:
        print(f"[writing] {base}: passive-heavy ({doc['passive_rate']}/100w); name the actor.")
    if doc.get("adverb_rate", 0) >= 5:
        print(f"[writing] {base}: adverb-heavy ({doc['adverb_rate']}/100w); prefer strong verbs.")

    return n_hit


def report_passes(path, high, medium, low, doc):
    """Editing-passes view (Ptacek): every category as a named pass with a count."""
    base = os.path.basename(path)
    tiers = [("HIGH", high), ("MED", medium), ("LOW", low)]
    by_cat = {}
    for tier, items in tiers:
        for f in items:
            key = (f["category"], tier if tier != "LOW" else "advisory")
            by_cat.setdefault(key, 0)
            by_cat[key] += 1
    print(f"[passes] {base}:")
    if not by_cat:
        print("  (all passes clear)")
    for (cat, tier), n in sorted(by_cat.items(), key=lambda kv: (-kv[1], kv[0][0])):
        print(f"  {n:>4}  {cat} [{tier}]")
    if doc.get("uniform"):
        print(f"  cadence: uniform (cv={doc.get('cv')})")
    if doc.get("repetitive_openers"):
        print(f"  openers: repetitive (ratio={doc.get('opener_ratio')})")


def main(argv):
    verbose = "--verbose" in argv or "-v" in argv
    as_json = "--json" in argv
    as_passes = "--passes" in argv
    as_score = "--score" in argv
    files = [a for a in argv if not a.startswith("-") and os.path.isfile(a)]
    if not files:
        return 0

    total = 0
    payload = []
    for path in files:
        try:
            with open(path, "rb") as fh:
                reason = binary_reason(fh.read(8192), name=path)
        except OSError:
            reason = "cannot read"
        if reason:
            print(f"[writing] {os.path.basename(path)}: cannot screen ({reason})")
            continue
        high, medium, low, doc = scan(path)
        total += len(high) + len(medium)
        if as_passes and not as_json:
            report_passes(path, high, medium, low, doc)
            continue
        if as_score and not as_json:
            base = os.path.basename(path)
            verdict = "clean" if (len(high) + len(medium)) == 0 else "flagged"
            print(f"[score] {base}: texture {doc.get('score', 0)}/100 "
                  f"({'elevated' if doc.get('elevated') else 'low'}), "
                  f"device-gate {verdict} "
                  f"[{len(high)}H/{len(medium)}M, {doc.get('soft', 0)} soft / "
                  f"{doc.get('words', 0)}w]")
            continue
        if as_json:
            payload.append({
                "file": path,
                "high": high,
                "medium": medium,
                "low": low,
                "cadence": doc,
                "clean": (len(high) + len(medium)) == 0,
            })
        else:
            report_text(path, high, medium, low, doc, verbose)

    if as_json:
        print(json.dumps({"files": payload, "total_hits": total}, ensure_ascii=False, indent=2))
    elif total:
        print(f"[writing] {total} HIGH/MEDIUM tell(s) across {len(files)} file(s). "
              f"These read as machine-written or break the plain-writing standard. "
              f"Rewrite plainly before this ships. Contrast pairs, setup/payoff, and "
              f"performed enthusiasm are not fully caught here; hold those by judgment.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
