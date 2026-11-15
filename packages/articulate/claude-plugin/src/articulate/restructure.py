"""Restructure guidance: move per-paragraph source, confidence and limit
sentences into one "Sources and method" section, word for word, with an
anchor left where each run stood.

propose() never edits a file and never rewords a sentence. Its output passes
verify_relocation(), a guard stricter than the editor's: every original
sentence appears exactly once and byte for byte, every paragraph stays, the
protected spans (citations, links, numbers, quotes, disclosures) are the same
multiset, and each anchor has exactly one entry. Any failure refuses the whole
proposal with named reasons.
"""
import difflib
import hashlib
import re

from . import corpus_features as cf
from .authorship import is_disclosure
from .meaning_guard import protected_spans

SCHEMA = "articulate/restructure/v2"
HEADING = "## Sources and method"
LIMIT = ("Moving a limit line changes where a reader meets it. Check that each claim still "
         "reads as bounded where it stands.")
ANCHOR = re.compile(r"\[\^m-([0-9a-f]{6,8})\](?!:)|\[\(source\)\]\(#m-([0-9a-f]{6,8})\)")
ENTRY = re.compile(r"^(?:\[\^m-([0-9a-f]{6,8})\]: |<a id=\"m-([0-9a-f]{6,8})\"></a> )", re.S)
_BLOCK_SPLIT = re.compile(r"\n[ \t]*\n")


def _offsets(text):
    out, pos = {}, 0
    for n, line in enumerate(text.split("\n"), 1):
        out[n] = pos
        pos += len(line) + 1
    return out


def _sources_lines(blocks):
    for i, b in enumerate(blocks):
        if b["kind"] == "heading" and cf.heading_key(b["text"]) == "sources and method":
            end = next((x["line_start"] - 1 for x in blocks[i + 1:] if x["kind"] == "heading"
                        and len(x["text"]) - len(x["text"].lstrip("#")) <= 2), 10 ** 9)
            return b["line_start"], end
    return None


def _movable(labels, texts):
    """Indices to move: scaffold sentences after a kept sentence, leaving a claim."""
    move, kept_before = set(), False
    for i, (lab, s) in enumerate(zip(labels, texts)):
        if lab in cf.SCAFFOLD_MOVES and kept_before and not is_disclosure(s):
            move.add(i)
        else:
            kept_before = True
    if not any(lab == "claim" for i, lab in enumerate(labels) if i not in move):
        return set()
    return move


def _runs(block, base):
    bounds = cf.sentence_bounds(block["text"])
    texts = [block["text"][a:b] for a, b in bounds]
    move = _movable([cf.label(s) for s in texts], texts) if len(texts) > 1 else set()
    runs, i = [], 0
    while i < len(texts):
        if i in move:
            j = i
            while j + 1 < len(texts) and j + 1 in move:
                j += 1
            runs.append((base + bounds[i - 1][1], base + bounds[j][1], " ".join(texts[i:j + 1]), j - i + 1))
            i = j + 1
        else:
            i += 1
    return runs


def _anchor_id(moved, seen):
    k = seen.get(moved, 0)
    seen[moved] = k + 1
    digest = hashlib.sha256(f"{moved}\x00{k}".encode("utf-8")).hexdigest()
    return digest


def _plan(text):
    blocks, offsets = cf.blocks(text), _offsets(text)
    skip = _sources_lines(blocks)
    plan, section, seen, used = [], "(top)", {}, set()
    for b in blocks:
        if b["kind"] == "heading":
            section = b["text"].strip()
        if b["kind"] != "prose" or is_disclosure(b["text"]):
            continue
        if skip and skip[0] <= b["line_start"] <= skip[1]:
            continue
        for start, end, moved, count in _runs(b, offsets[b["line_start"]]):
            digest = _anchor_id(moved, seen)
            rid = digest[:6] if digest[:6] not in used else digest[:8]
            used.add(rid)
            plan.append({"id": rid, "start": start, "end": end, "text": moved, "sentences": count,
                         "section": section, "line": b["line_start"]})
    return plan, skip


def _anchor(rid, style):
    return f"[^m-{rid}]" if style == "footnote" else f"[(source)](#m-{rid})"


def _entry(item, style):
    prefix = f"[^m-{item['id']}]: " if style == "footnote" else f'<a id="m-{item["id"]}"></a> '
    return prefix + item["text"]


def _apply(text, plan, skip, style):
    pieces, last = [], 0
    for item in plan:
        pieces += [text[last:item["start"]], _anchor(item["id"], style)]
        last = item["end"]
    body = "".join(pieces) + text[last:]
    entries = "\n\n".join(_entry(i, style) for i in plan)
    if skip is None:
        return body.rstrip("\n") + f"\n\n{HEADING}\n\n{entries}\n"
    lines = body.split("\n")
    at = next(i for i, line in enumerate(lines)
              if line.lstrip().startswith("#") and cf.heading_key(line) == "sources and method")
    end = next((j for j in range(at + 1, len(lines)) if re.match(r"#{1,2}\s", lines[j])), len(lines))
    head = "\n".join(lines[:end]).rstrip("\n")
    tail = "\n".join(lines[end:])
    return head + "\n\n" + entries + "\n" + ("\n" + tail if tail.strip() else "")


def _scaffold_share(text):
    paras = [b for b in cf.prose_blocks(text) if len(cf.sentences(b["text"])) >= 2]
    if not paras:
        return 0.0
    return round(sum(cf.is_scaffold(cf.move_sequence(b["text"])) for b in paras) / len(paras), 3)


def propose(text, anchors="footnote"):
    """A relocation proposal, its diff, its summary and its guard verdict."""
    from .corpus_receipt import corpus_fingerprint
    if anchors not in ("footnote", "link"):
        raise ValueError("anchors must be footnote or link")
    if not isinstance(text, str):
        raise ValueError("restructure needs document text")
    text = text.replace("\r\n", "\n")
    plan, skip = _plan(text)
    proposal = _apply(text, plan, skip, anchors) if plan else text
    verdict = verify_relocation(text, proposal)
    if not verdict["ok"]:
        proposal, plan = text, []
    by_section = {}
    for item in plan:
        by_section[item["section"]] = by_section.get(item["section"], 0) + item["sentences"]
    body = proposal.split(HEADING)[0]
    return {"schema": SCHEMA, "input_sha256": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "fingerprint": corpus_fingerprint(), "anchors": anchors, "proposal": proposal,
            "moved": [{k: i[k] for k in ("id", "line", "section", "sentences")} for i in plan],
            "summary": {"moved_sentences": sum(i["sentences"] for i in plan), "by_section": by_section,
                        "scaffold_share_before": _scaffold_share(text),
                        "scaffold_share_after": _scaffold_share(body), "scope": LIMIT},
            "verdict": verdict, "ai_detector_consulted": False,
            "diff": "".join(difflib.unified_diff(text.splitlines(keepends=True),
                                                 proposal.splitlines(keepends=True),
                                                 "original", "proposed"))}


def _split_entries(proposed):
    """Body blocks, entry texts by id, and duplicate entry ids."""
    body, entries, dupes = [], {}, []
    for block in _BLOCK_SPLIT.split(proposed):
        m = ENTRY.match(block)
        if not m:
            body.append(block)
            continue
        rid = m.group(1) or m.group(2)
        if rid in entries:
            dupes.append(rid)
        entries[rid] = block[m.end():].rstrip("\n")
    return body, entries, dupes


def _flat(text):
    return " ".join(text.split())


def _span_multiset(text):
    """Protected spans found block by block, so a quote mark left open in one
    paragraph cannot make a span that depends on the blank lines between blocks."""
    return sorted((s["kind"], s["text"]) for block in _BLOCK_SPLIT.split(text) if block.strip()
                  for s in protected_spans(block))


def _anchor_reasons(body, entries, dupes):
    ids = [m.group(1) or m.group(2) for m in ANCHOR.finditer(body)]
    reasons = [f"anchor m-{i} has no entry" for i in sorted(set(ids) - set(entries))]
    reasons += [f"entry m-{i} has no anchor" for i in sorted(set(entries) - set(ids))]
    reasons += [f"anchor m-{i} used more than once" for i in sorted({i for i in ids if ids.count(i) > 1})]
    reasons += [f"entry m-{i} appears more than once" for i in sorted(set(dupes))]
    return reasons


def _sentence_reasons(original, body, entries):
    rebuilt = ANCHOR.sub(lambda m: " " + entries.get(m.group(1) or m.group(2), ""), body)
    if _flat(rebuilt) != _flat(original):
        return ["sentence missing, added, changed or out of order"]
    pool = ANCHOR.sub("", body) + "\n" + "\n".join(entries.values())
    for b in cf.blocks(original):
        for s in cf.sentences(b["text"]):
            if pool.count(s) != original.count(s):
                return ["sentence missing, added, changed or out of order"]
    return []


def verify_relocation(original, proposed):
    """ok and named reasons for a relocation proposal against its original."""
    original, proposed = original.replace("\r\n", "\n"), proposed.replace("\r\n", "\n")
    blocks, entries, dupes = _split_entries(proposed)
    added_heading = HEADING not in original
    body = "\n\n".join(b for b in blocks if not (added_heading and b.strip() == HEADING))
    reasons = _anchor_reasons(body, entries, dupes)
    reasons += _sentence_reasons(original, body, entries)
    moved = ANCHOR.sub("", body) + "\n\n" + "\n\n".join(entries.values())
    if _span_multiset(original) != _span_multiset(moved):
        reasons.append("protected spans changed (citations, links, numbers, quotes or disclosures)")
    if len([b for b in _BLOCK_SPLIT.split(original) if b.strip()]) != len([b for b in _BLOCK_SPLIT.split(body) if b.strip()]):
        reasons.append("paragraph count changed")
    return {"ok": not reasons, "reasons": reasons}
