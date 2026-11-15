"""Promotional-template checks for short social text.

check(text) returns span findings in the detector's record shape, each with a
`cost` field that says what the pattern takes from a reader. The checks look at
form: a hype opener, a capitalised claim beside a spec number, stock launch-copy
formulas, and endorsement wording with no disclosure marker in the text. A hit
says the text uses a promotional template. It says nothing about who wrote it,
whether anyone was paid, or whether the claim is true.
"""
import re

CATEGORY = "promo"

# Each rule: (label, compiled pattern, weight, cost to the reader).
_I = re.IGNORECASE
HYPE_OPENERS = [
    ("hype opener: address word",
     re.compile(r"^\s*(sir|bro|guys|fam|ser|anon|frens?)\b[\s.,!…]*", _I), 2,
     "the opener performs excitement before it gives the reader any fact"),
    ("hype opener: alarm",
     re.compile(r"^\s*(\U0001F6A8|BREAKING\b|HUGE\b|this is (huge|insane|wild|massive)\b"
                r"|holy (sh\w*|cow)\b|lfg\b|wait what\b)", _I), 2,
     "the opener signals urgency that the rest of the post must then earn"),
    ("hype opener: drop announcement",
     re.compile(r"\b(they|\w+) (just|finally) (dropped|shipped|released|launched)\b", _I), 1,
     "the drop framing sells novelty and leaves out what changed"),
]

LAUNCH_FORMULAS = [
    ("launch formula: fundamental bottleneck",
     re.compile(r"\bis the (fundamental|biggest|real|core) bottleneck (for|in|of)\b", _I), 2,
     "a sweeping premise the post never supports, set up so the product can resolve it"),
    ("launch formula: the infra that solves it",
     re.compile(r"\b(will be|is|becomes) the (infra|infrastructure|platform|layer|rails)"
                r" that (solves|fixes|powers|unlocks)\b", _I), 2,
     "a promise of category ownership with no evidence the reader can check"),
    ("launch formula: we spent the last N years",
     re.compile(r"\bwe('ve)? spent the (last|past) (\w+|\d+) (years?|months?) building\b", _I), 2,
     "effort stands in for results; time spent tells the reader nothing about quality"),
    ("launch formula: the best solution",
     re.compile(r"\bthe (best|only|ultimate) (solution|platform|tool|way) for\b", _I), 2,
     "an unqualified superlative with no comparison named"),
    ("launch formula: best-in-class",
     re.compile(r"\b(best[- ]in[- ]class|state[- ]of[- ]the[- ]art|world[- ]class"
                r"|game[- ]?changer|next[- ]level)\b", _I), 1,
     "a ranking claim with no benchmark, baseline or rival named"),
    ("launch formula: introducing X, its first Y",
     re.compile(r"\b(introducing|meet|say hello to)\b[^.\n]{0,60}?\b(first|newest|latest)\b"
                r"[^.\n]{0,20}?:", _I), 2,
     "press-release voice; the reader cannot tell who is speaking for whom"),
    ("launch formula: X launches Y, its first Z",
     re.compile(r"\b(launch(es|ed)|unveil(s|ed)|release[sd])\b[^.\n]{0,60}?,\s*(its|their)"
                r" (first|newest|latest)\b", _I), 2,
     "press-release summary voice in a personal post"),
    ("launch formula: built with our",
     re.compile(r"\bbuilt (with|on) our (own )?(automated|proprietary|in-house|novel)\b", _I), 1,
     "an origin story offered in place of a result"),
    ("launch formula: excited to announce",
     re.compile(r"\b(we're|we are|i'm|i am) (so |super |incredibly )?(thrilled|excited|proud)"
                r" to (announce|introduce|share|launch)\b", _I), 1,
     "the announcement leads with the poster's feelings before the reader's gain"),
]

# A spec number with a unit, the kind a launch claim hangs on.
SPEC = re.compile(r"\b\d[\d,.]*\s?(tokens?/s(ec)?|tok/s|t/s|x faster|x cheaper|%|ms|fps"
                  r"|[kmb] params|b parameters|gb|tb|tflops|qps|rps)\b|\b\d+x\b", _I)
CAPS = re.compile(r"\b[A-Z]{4,}\b")
ACRONYMS = {"HTTP", "JSON", "HTML", "NASA", "GPUS", "CUDA", "TFLOPS", "API", "LLMS", "SDK"}

ENDORSE = re.compile(
    r"\b(you (need|have|gotta|got) to (try|check)|go (check|try) (it|this|them) out"
    r"|use (my )?code\b|link (in|below)|check (it|them) out\b|can'?t recommend .{0,20} enough"
    r"|this changes everything|don'?t sleep on|i'?ve been using .{0,30} and (it|i))", _I)
DISCLOSURE = re.compile(
    r"(#ad\b|#sponsored|#partner|#paid|paid partnership|sponsored by|in partnership with"
    r"|\bdisclosure\b|\bi was paid\b|\bthey paid me\b|\bi('m| am) an? (advisor|investor|employee)"
    r"|\bi work (at|for)\b|\baffiliate\b|\bgifted\b)", _I)

DOES_NOT_PROVE = ("A promotional-template hit says the text uses launch-copy or endorsement "
                  "form. It does not show that anyone was paid, that the poster is a bot, or "
                  "that the claim is false. Real founders write launch posts, and real fans "
                  "write with excitement.")


def _rec(text, m, label, weight, cost):
    start, end = m.span()
    line = text.count("\n", 0, start) + 1
    col = start - (text.rfind("\n", 0, start) + 1) + 1
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:48]
    return {"line": line, "col": col, "start": start, "end": end,
            "category": CATEGORY, "label": label, "match": m.group(0).strip(),
            "rule_id": f"{CATEGORY}/{slug}", "weight": weight, "cost": cost,
            "tier": "high" if weight >= 2 else "medium"}


def _caps_spec(text):
    """A shouted word and a spec number in one sentence: the claim-and-spec shape."""
    out = []
    for sent in re.finditer(r"[^.!?\n]+[.!?\n]?", text):
        s = sent.group(0)
        caps = [c for c in CAPS.finditer(s) if c.group(0) not in ACRONYMS]
        spec = SPEC.search(s)
        if caps and spec:
            m = re.compile(re.escape(caps[0].group(0))).search(text, sent.start())
            r = _rec(text, m, "claim and spec number", 2,
                     "an emphasised claim leans on a figure the post gives no conditions for")
            r["match"] = f"{caps[0].group(0)} ... {spec.group(0)}"
            out.append(r)
    return out


def check(text):
    """Return promotional-template findings for one short text, in text order."""
    found = []
    for label, pat, w, cost in HYPE_OPENERS + LAUNCH_FORMULAS:
        for m in pat.finditer(text):
            found.append(_rec(text, m, label, w, cost))
    found += _caps_spec(text)
    endorse = list(ENDORSE.finditer(text))
    voice = [f for f in found if f["label"].startswith("launch formula: introducing")
             or f["label"].startswith("launch formula: X launches")]
    if (endorse or voice) and not DISCLOSURE.search(text):
        m = endorse[0] if endorse else None
        if m is not None:
            r = _rec(text, m, "endorsement without disclosure", 2,
                     "the reader cannot weigh a recommendation without knowing the "
                     "poster's stake")
        else:
            r = dict(voice[0], label="endorsement without disclosure",
                     rule_id=f"{CATEGORY}/endorsement-without-disclosure", weight=2,
                     cost="speaking for a product in its own launch voice, with no stated "
                          "stake, hides who benefits", tier="high")
        found.append(r)
    found.sort(key=lambda f: (f["start"], f["label"]))
    return found


def score(findings):
    return sum(f["weight"] for f in findings)


def assess(text, threshold=3):
    """One item's promo verdict: findings, score, and whether it reads as a template."""
    f = check(text)
    s = score(f)
    return {"findings": f, "score": s, "template": s >= threshold}
