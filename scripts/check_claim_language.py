#!/usr/bin/env python3
"""check_claim_language.py -- the gate that keeps a claim from growing in retelling.

Every checker in this repository verifies a SUBMITTED object. None decides
optimality. The crossing checker verifies the crossing count of a drawing and not
the rectilinear crossing number of the graph. The Zarankiewicz checker verifies
K_{2,2}-freeness and an edge count, not z(m,n;2,2). The matmul checker verifies
that a scheme is exact, not that its rank is minimal.

That distinction is the single most likely thing to be lost when a result is
retold, because "found a drawing with 103 crossings" compresses naturally and
wrongly into "found the crossing number". A note in a document does not stop that.
A gate does.

So: on PUBLIC surfaces, the bare phrases below may not appear unless the same
sentence also carries a disclaimer. The list of disclaimers is deliberately short
and specific, so "we computed the crossing number" cannot be excused by a vague
nearby hedge.

Internal documents are not scanned. Working notes need to be able to discuss the
mathematics in its own vocabulary. What ships is what is gated.

Exit 0 clean, 1 with violations listed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# PUBLIC surfaces only. A shipped page, a released model card, the top-level
# readme. project-docs/records and project-docs/prereg are internal by register
# and are not scanned.
PUBLIC_GLOBS = (
    "README.md",
    "project-docs/releases/**/shipped-page/**/*.md",
    "project-docs/releases/**/MODEL_CARD.md",
    "project-docs/releases/**/README.md",
    "site/**/*.md",
    "site/**/*.html",
)

# A claim, and the honest phrasing it must be replaced by.
CLAIMS = (
    (r"\brectilinear crossing numbers?\b", "the crossing count of the submitted drawing"),
    (r"\bcrossing numbers?\s+of\b", "the crossing count of the submitted drawing"),
    (r"\bzarankiewicz numbers?\b", "a verified K_{2,2}-free graph with N edges"),
    (r"\boptimal (?:drawing|graph|scheme|construction|certificate)\b",
     "the best VERIFIED value we have seen"),
    (r"\b(?:minimum|minimal|fewest possible|maximum possible)\s+"
     r"(?:crossings?|edges?|rank)\b", "the best VERIFIED value we have seen"),
    (r"\bproves?\s+optimality\b", "nothing here proves optimality"),
    (r"\bwe\s+(?:solved|proved)\s+(?:the\s+)?(?:open\s+)?problem\b",
     "we verified a submitted construction"),
)

# Words that license a mention, because the sentence is disclaiming rather than
# claiming. Short and specific on purpose.
DISCLAIMERS = (
    "not claimed", "not computed", "not bounded", "do not claim", "does not claim",
    "no claim", "not proven", "not proved", "cannot claim", "never claimed",
    "submitted drawing", "submitted graph", "submitted scheme", "submitted object",
    "not optimality", "without claiming", "makes no claim",
)


def sentences(text: str):
    """(sentence_with_whitespace_collapsed, line_number).

    Split on sentence-ending punctuation ONLY, never on newlines. Markdown wraps
    prose mid-sentence, so splitting on newlines separates a claim from the
    disclaimer that licenses it and the gate reports a violation against text
    that is already correct. That happened on the first run of this script
    against its own fixture, and a gate with false positives is a gate somebody
    switches off.
    """
    offset = 0
    for chunk in re.split(r"(?<=[.!?])(?=\s)", text):
        yield " ".join(chunk.split()), offset
        offset += len(chunk)


def scan(path: Path) -> list:
    out = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for sentence, offset in sentences(text):
        low = sentence.lower()
        if any(d in low for d in DISCLAIMERS):
            continue
        for pattern, instead in CLAIMS:
            m = re.search(pattern, low)
            if m:
                # Locate the phrase in the ORIGINAL text so the reported line is
                # where the claim actually sits, not where its sentence began.
                raw = re.search(pattern, text[offset:].lower())
                at = offset + (raw.start() if raw else 0)
                line = text.count("\n", 0, at) + 1
                out.append(f"{path.relative_to(ROOT).as_posix()}:{line} "
                           f"says {m.group(0)!r}; say {instead!r} "
                           f"or add a disclaimer in the same sentence")
    return out


def public_files() -> list:
    seen: dict = {}
    for pattern in PUBLIC_GLOBS:
        for p in ROOT.glob(pattern):
            if p.is_file():
                seen[p.resolve()] = p
    return sorted(seen.values())


def main() -> int:
    files = public_files()
    violations: list = []
    for p in files:
        violations.extend(scan(p))
    print(f"claim-language gate: scanned {len(files)} public surface(s)")
    if violations:
        print("A CLAIM ON A PUBLIC SURFACE THAT NO RECEIPT SUPPORTS:")
        for v in violations:
            print("  " + v)
        print("\nEvery checker here verifies a SUBMITTED object. None decides "
              "optimality.")
        return 1
    print("no optimality claim on any public surface: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
