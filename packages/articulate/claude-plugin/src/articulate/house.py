"""The house voice applied to model output: a deterministic transform, located
notes, and a receipt.

transform runs the closed edit list from house_edits on text a model wrote,
verifies the candidate edit by edit, runs the meaning guard on the paragraphs
left in place, and returns the text with notes and an
articulate/house-receipt/v1 receipt. When any check fails it returns the
original text and names the reason. Everything else the spec asks for is a
note for the model, never an edit: the style rules' findings, and any
sentence that claims a human life (house/human-claim).

The house voice applies only to the model's own speech. It never reads the
personal voice store, and it is never applied to text a user wrote.
"""
import hashlib
import re
import time

from . import checkext, detector, house_edits, house_settings
from .house_spec import (BRIEF_CEILING, CURRENT, brief, default_tuning,  # noqa: F401
                         fingerprint, session_context, spec, versions)
from .house_edits import verify_edits  # noqa: F401  (part of this module's interface)

RECEIPT = "articulate/house-receipt/v2"
RECEIPT_V1 = "articulate/house-receipt/v1"
SCOPE = ("Applies exact edits from a closed list. A lexical meaning guard checks each "
         "paragraph that the edits leave in place.")
_HUMAN = [re.compile(p, re.I) for p in spec()["human_claims"]]
_FENCE = re.compile(r"(?m)^[ \t]*(```|~~~)")


def _sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def human_claims(text):
    """Located notes for sentences that claim a human life or experience."""
    notes = []
    for n, line in enumerate(text.split("\n"), 1):
        for p in _HUMAN:
            m = p.search(line)
            if m:
                notes.append({"category": "house/human-claim", "line": n, "match": m.group(),
                              "reason": "the house voice is a model's voice and claims no life"})
                break
    return notes


# The house voice is a model's speech in conversation, so its notes come from
# the default rules plus the structure pack that the chat profile carries.
_NOTE_PROFILE = {"rule_packs": ("structure",)}


def style_notes(text, tiers=("high", "medium")):
    result = checkext.check_text(text, profile=dict(_NOTE_PROFILE))
    return [{"category": "style/" + str(f.get("category")), "line": f["line"],
             "match": f["match"][:80], "reason": f["label"], "tier": tier}
            for tier in tiers for f in result[tier]]


def _settings(settings):
    # A direct call is an explicit request, so it opts in (house_settings.for_request).
    return house_settings.for_request() if settings is None else settings


def _counts(notes):
    out = {}
    for n in notes:
        out[n["category"]] = out.get(n["category"], 0) + 1
    return out


def _receipt(text, out, settings, edits, refused, notes, started):
    return {"schema": RECEIPT, "house_version": spec()["version"],
            "house_fingerprint": fingerprint(settings),
            "ruleset_version": detector.ruleset_fingerprint(),
            "mode": settings["mode"], "settings": {"mode": settings["mode"],
                                                   "tuning": dict(settings["tuning"])},
            "input_sha256": _sha(text), "output_sha256": _sha(out),
            "edits": [{"rule": e["rule"], "start": e["start"], "end": e["end"],
                       "removed_sha256": _sha(text[e["start"]:e["end"]])} for e in edits],
            "refused": refused, "notes_by_category": _counts(notes),
            "human_claim_notes": sum(1 for n in notes if n["category"] == "house/human-claim"),
            "timing_ms": round((time.perf_counter() - started) * 1000, 3),
            "ai_detector_consulted": False, "scope": SCOPE}


def _edits_for(text, at_start=True, at_end=True):
    return house_edits.compute_part(text, at_start, at_end)


def transform(text, settings=None, *, at_start=True, at_end=True, notes=True):
    """{text, edits, refused, notes, receipt} for one piece of model output."""
    if not isinstance(text, str):
        raise ValueError("house transform needs text")
    started = time.perf_counter()
    settings = _settings(settings)
    if settings["mode"] == "off":
        return {"text": text, "edits": [], "refused": [], "notes": [],
                "receipt": _receipt(text, text, settings, [], [], [], started)}
    edits = _edits_for(text, at_start, at_end)
    candidate = house_edits.apply(text, edits)
    verdict = verify_edits(text, candidate, edits)
    refused = [] if verdict["ok"] else verdict["reasons"]
    if not refused and at_start and at_end and text.strip() and not candidate.strip():
        # A reply that is nothing but residue keeps its words: an empty reply
        # tells the reader less than a stock sentence does.
        refused = ["the edits would leave no text"]
    if refused:
        candidate, edits = text, []
    found = (human_claims(candidate) + style_notes(candidate)) if notes else []
    return {"text": candidate, "edits": edits, "refused": refused, "notes": found,
            "receipt": _receipt(text, candidate, settings, edits, refused, found, started)}


def revision_findings(text):
    """What the Stop hook asks a model to revise: human-life claims and the
    style rules' HIGH findings. Empty when the reply is clean."""
    return human_claims(text) + style_notes(text, tiers=("high",))


def _boundary(buf):
    """Index just past the last paragraph break outside a code fence, or -1."""
    best = -1
    for m in house_edits._PARAGRAPH.finditer(buf):
        if len(_FENCE.findall(buf[:m.start()])) % 2 == 0:
            best = m.start()
    return best


def transform_stream(chunks, settings=None):
    """Yield transformed text as paragraphs complete. The last paragraph is
    held back until the stream ends, since only then is it known to be last."""
    settings = _settings(settings)
    buf, started, held = "", False, ""
    for chunk in chunks:
        buf += chunk
        cut = _boundary(buf)
        if cut > 0:
            head, buf = buf[:cut], buf[cut:]
            out = transform(head, settings, at_start=not started, at_end=False, notes=False)["text"]
            if not started and not out.strip():
                # Everything so far was opener residue: its paragraph break goes too.
                # The words are held, not dropped, in case nothing else follows.
                sep = house_edits._PARAGRAPH.match(buf).end()
                held, buf = held + head + buf[:sep], buf[sep:]
                out = ""
            started = started or bool(out.strip())
            yield out
    if not started and (held or buf):
        # Nothing but the last part remains: transform the whole reply at once, so
        # a reply made only of residue is kept exactly as the whole transform keeps it.
        yield transform(held + buf, settings, notes=False)["text"]
    elif buf:
        yield transform(buf, settings, at_start=False, at_end=True, notes=False)["text"]


def verify_receipt(receipt, text):
    """(Match | Drift | Unverifiable, detail) for a house receipt and its input."""
    if not isinstance(receipt, dict) or receipt.get("schema") not in (RECEIPT, RECEIPT_V1):
        return "Unverifiable", "not an articulate house receipt"
    version = receipt.get("house_version")
    if version not in versions():
        return "Unverifiable", "receipt names %s; this install has %s" % (
            version, ", ".join(versions()))
    if receipt.get("input_sha256") != _sha(text):
        return "Drift", "the text differs from the input the receipt names"
    try:
        settings = house_settings.validate(receipt.get("settings", {}))
    except ValueError as exc:
        return "Unverifiable", "receipt settings: %s" % exc
    settings = dict(settings, tuning=dict(default_tuning(version), **settings["tuning"]))
    if fingerprint(settings, version) != receipt.get("house_fingerprint"):
        return "Unverifiable", "the house spec or settings fingerprint differs"
    # Every version shares one edit list (a test holds this), so the current
    # transform re-derives the output of a receipt made under an older version.
    redo = transform(text, settings, notes=False)["receipt"]
    same = redo["output_sha256"] == receipt.get("output_sha256") and \
        [(e["rule"], e["start"], e["end"]) for e in redo["edits"]] == \
        [(e.get("rule"), e.get("start"), e.get("end")) for e in receipt.get("edits", [])]
    return ("Match", "output and edits re-derive") if same else ("Drift", "output differs on replay")
