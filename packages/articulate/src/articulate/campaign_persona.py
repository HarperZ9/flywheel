"""Persona-bio template checks: the stock-persona slot grammar.

parse(bio) finds the slots a stock persona fills (age, role, hobby, token, and a
pet or tagline line) and returns them with the frame: the bio with each slot
value replaced by its slot name. Slots key on structure and on stock phrasing
only. Which place, language, script or name fills a slot is never a feature: a
place is masked to <PLACE> and carries no weight, and no rule reads the script.

assess(bio) counts filled slot types. A bio reads as a stock persona when it
fills several slot types from stock frames. A real person who mentions crypto
fills one slot; the template fills four or five.
"""
import re

CATEGORY = "persona"
_I = re.IGNORECASE

# (slot, label, pattern). Every pattern is a stock frame; the value inside is masked.
SLOTS = [
    ("age", "age slot", re.compile(
        r"\b(age \d{2}|\d{2}[- ]?(year[- ]old|years? old|yo|y/o)|\d{2}\s*years? young)\b", _I)),
    ("age", "age tagline", re.compile(r"\bstill young at heart\b", _I)),
    ("role", "role-in-place frame", re.compile(
        r"\b([Aa]n?)\s+([A-Z][\w-]+(\s[A-Z][\w-]+)?)\s+(in|from|based in)\s+([A-Z][\w-]+)")),
    ("role", "dreamer role", re.compile(
        r"\b(\d{2}[- ]year[- ]old |a |an )?(dreamer|hustler|believer|visionary|degen)\b", _I)),
    ("hobby", "passionate-about frame", re.compile(
        r"\b(passionate about|enjoying life with|obsessed with|in love with|lover of"
        r"|addicted to|living for|fan of)\s+([\w$#][\w$# -]{1,30})", _I)),
    ("token", "token ticker", re.compile(r"(?<![\w$])\$[A-Z]{2,6}\b")),
    ("token", "stacking frame", re.compile(
        r"\b(stacking|stacking up|hodling|holding|accumulating)\s+\$?[A-Z]{2,6}\b", _I)),
    ("token", "crypto-is-the-future tagline", re.compile(
        r"\b(crypto|web3|bitcoin|blockchain|defi) (is the future|will change the world"
        r"|forever|to the moon)\b", _I)),
    ("token", "chasing frame", re.compile(r"\bchasing (dreams|gains|the moon|bags)\b", _I)),
    ("tagline", "like-a-pro tagline", re.compile(r"\blike a (pro|boss|legend)\b", _I)),
    ("tagline", "memes tagline", re.compile(r"\bhere for the (memes|vibes|gains|culture)\b", _I)),
    ("tagline", "pet tagline", re.compile(
        r"\b(cat|dog) (person|lover|mom|dad|parent)\b|\bproud (cat|dog) (mom|dad|owner)\b", _I)),
    ("tagline", "traveler tagline", re.compile(r"\b(traveler|traveller|wanderer|explorer)\b", _I)),
    ("tagline", "pipe-separated tagline", re.compile(r"\s\|\s*[A-Z][\w ]{2,25}\.?\s*$")),
]

# Values masked out of the frame, so two bios that differ only in fillers share a frame.
_MASKS = [
    (re.compile(r"\b\d{2}\b"), "<N>"),
    (re.compile(r"(?<![\w$])\$?[A-Z]{2,6}\b"), "<TOKEN>"),
    (re.compile(r"\b(in|from|based in)\s+[A-Z][\w-]+"), r"\1 <PLACE>"),
    (re.compile(r"\b([Aa]n?)\s+[A-Z][\w-]+(\s[A-Z][\w-]+)?\s+(in|from|based in)\b"), r"a <ROLE> \3"),
    (re.compile(r"\b(passionate about|enjoying life with|obsessed with|in love with|lover of"
                r"|addicted to|living for|fan of)\s+[\w$#][\w$#-]*", _I), r"\1 <HOBBY>"),
]

DOES_NOT_PROVE = ("Slot hits say a bio follows a stock-persona form. They do not show the "
                  "account is automated or fake: plenty of people write template-shaped "
                  "bios, and a bot can carry a hand-written one.")

COST = ("a stock-persona bio tells the reader nothing particular about the person, so it "
        "lends an account the look of a person without the content of one")

# Per-platform defaults. A platform changes how long a bio can run and how many
# slot types a stock persona must fill before the bio is flagged.
PLATFORMS = {
    "x": {"max_chars": 160, "min_slots": 3},
    "reddit": {"max_chars": 200, "min_slots": 3},
    "tiktok": {"max_chars": 80, "min_slots": 3},
    "linkedin": {"max_chars": 2600, "min_slots": 4},
    "generic": {"max_chars": 2600, "min_slots": 3},
}


def frame(bio):
    out = bio
    for pat, rep in _MASKS:
        out = pat.sub(rep, out)
    return re.sub(r"\s+", " ", out).strip().lower()


def parse(bio):
    hits = []
    for slot, label, pat in SLOTS:
        for m in pat.finditer(bio):
            hits.append({"slot": slot, "label": label, "start": m.start(), "end": m.end(),
                         "match": m.group(0).strip()})
    hits.sort(key=lambda h: (h["start"], h["slot"]))
    return {"slots": hits, "slot_types": sorted({h["slot"] for h in hits}),
            "frame": frame(bio)}


def assess(bio, platform="generic"):
    cfg = PLATFORMS.get(platform, PLATFORMS["generic"])
    p = parse(bio)
    n = len(p["slot_types"])
    template = n >= cfg["min_slots"]
    findings = []
    if template:
        first = p["slots"][0]
        findings.append({
            "line": 1, "col": first["start"] + 1, "start": first["start"],
            "end": p["slots"][-1]["end"], "category": CATEGORY,
            "label": f"stock-persona bio: {n} slot types filled ({', '.join(p['slot_types'])})",
            "match": bio[first["start"]:p["slots"][-1]["end"]],
            "rule_id": f"{CATEGORY}/stock-persona-bio", "weight": n, "cost": COST,
            "tier": "high"})
    return dict(p, findings=findings, score=n, template=template, platform=platform
                if platform in PLATFORMS else "generic")
