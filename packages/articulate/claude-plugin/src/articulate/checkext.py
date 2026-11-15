"""The check behind every command: the pinned detector, then the rule layer.

`check_text` runs articulate.detector.check_text unchanged. When the profile
switches on rules outside the detector (domain rule packs, project
terminology), it scans for them with articulate.rules_ext, adds the findings
by tier, and recomputes clean, gate, blocking_count and verdict with the same
logic the detector uses: GATE_TIERS for the profile's slop, gate_promote, and
MIN_WORDS_FOR_VERDICT. These findings never feed the texture score, which
stays the pinned detector's figure. A result that ran rule packs or project
terminology therefore carries `pack_findings`, the count of those findings by
tier, so a texture score of 0 is never the only figure beside a blocked gate.
With no such rules the detector's result is returned as it is, so output
stays byte-identical.

`analyze_blocks` gives the per-paragraph view under the same rules.

Before the detector runs, articulate.mdstructure blanks Markdown structure the
detector reads as prose (table delimiter rows, indented code, TOML front
matter) and hides register words that sit inside a capitalised name. The masks
keep every offset, and `match` and `snippet` come back from the original text.
Text with none of that structure gives the same result as before. Pass
`structure=False` for the unmasked result, which a receipt made before
STRUCTURE_VERSION existed replays against. Standard library only.
"""
from . import calibration, detector, mdstructure, pack_structure, rules_ext

STRUCTURE_VERSION = mdstructure.VERSION
CALIBRATION_VERSION = calibration.VERSION

_TIERS = (("high", "HIGH"), ("medium", "MEDIUM"), ("low", "LOW"))


def _regate(result, profile):
    slop = profile.get("slop", "flavored")
    gate = detector.GATE_TIERS.get(slop, frozenset({"HIGH"}))
    promote = set(profile.get("gate_promote", ()))
    blocking = 0
    for key, tier in _TIERS:
        if tier in gate:
            blocking += len(result[key])
        elif promote:
            blocking += sum(1 for f in result[key] if f["category"] in promote)
    n_dev = len(result["high"]) + len(result["medium"])
    if n_dev:
        verdict = "flagged"
    elif not result["sufficient"] and not result["low"]:
        verdict = "unverifiable"
    else:
        verdict = "clean"
    result.update(clean=n_dev == 0, gate="blocked" if blocking else "ok",
                  blocking_count=blocking, verdict=verdict)
    return result


def pack_findings(result):
    """{"high", "medium", "low"} counts of the findings that came from rule
    packs and project terminology. None of them is in the texture score."""
    outside = rules_ext.categories() | {"terminology"}
    return {key: sum(1 for f in result[key] if f["category"] in outside) for key, _t in _TIERS}


def _version(structure):
    """The mask version for a `structure` argument: True means the current one."""
    return mdstructure.VERSION if structure is True else structure


def _names(work, profile, allow, version=mdstructure.VERSION, known=None):
    """(text, detector result). A second pass runs only when a register word sits
    inside a capitalised name, with that name hidden."""
    result = detector.check_text(work, profile=profile, allow=allow)
    spans = mdstructure.name_spans(work, result, version, known)
    if spans:
        work = mdstructure.mask_spans(work, spans)
        result = detector.check_text(work, profile=profile, allow=allow)
    return work, result


def _calibrate(result, work, profile, version):
    """Apply the calibration layer and recompute the gate when it moved a finding."""
    if version and calibration.apply(result, work, _calibration(version)):
        result = _regate(result, profile or {})
        result["calibration"] = _calibration(version)
    return result


def _calibration(version):
    """The calibration version for a `calibration` argument: True means the current one."""
    return calibration.VERSION if version is True else version


def _run(text, work, profile, allow, structure, known=None, calib=True):
    """The check of `text`, scanning `work`, its structure-masked copy."""
    if structure:
        work, result = _names(work, profile, allow, _version(structure), known)
    else:
        result = detector.check_text(work, profile=profile, allow=allow)
    if rules_ext.active(profile):
        extra = rules_ext.scan(work, work.splitlines(keepends=True), profile)
        for (key, tier), found in zip(_TIERS, extra):
            result[key] = result[key] + [detector._finding(tier, f) for f in found]
        result = _regate(result, profile)
        if pack_structure.NAME in (profile.get("rule_packs") or ()):
            prose = list(rules_ext.prose_lines(work.splitlines(keepends=True)))
            result["cadence"] = dict(result["cadence"], **pack_structure.cadence(prose))
    result = _calibrate(result, work, profile, calib)
    if rules_ext.active(profile):
        result["pack_findings"] = pack_findings(result)
    return mdstructure.restore(result, text, work)


def changes_text(text):
    """True when the masks change this text, so a receipt must name them."""
    work = mdstructure.mask_structure(text)
    return _names(work, None, ())[0] != text


def calibration_changes(text, *, profile=None, allow=()):
    """True when the calibration layer moves a finding in this text, so a receipt
    must name its version."""
    return "calibration" in check_text(text, profile=profile, allow=allow)


def check_text(text, *, profile=None, allow=(), structure=True, calibration=True):
    """detector.check_text plus the profile's rule packs and terminology.
    `structure` is True for the current Markdown masks, a version name such as
    "markdown/1" for an older set, or False for none. `calibration` is True for
    the current calibration layer, a version name, or False for none; a result
    the layer changed carries a `calibration` field naming the version."""
    work = mdstructure.mask_structure(text, _version(structure)) if structure else text
    return _run(text, work, profile, allow, structure, calib=calibration)


def analyze_blocks(text, *, profile=None, allow=(), structure=True, calibration=True):
    """detector.analyze_blocks under the same rule layers as check_text."""
    if not structure and not calibration and not rules_ext.active(profile):
        return detector.analyze_blocks(text, profile=profile, allow=allow)
    work = mdstructure.mask_structure(text, _version(structure)) if structure else text
    known = mdstructure.known_names(work) if structure and structure != "markdown/1" else None
    out = []
    for b in detector.segment_blocks(work):
        r = _run(text[b["start"]:b["end"]], work[b["start"]:b["end"]], profile, allow,
                 structure, known, calibration)
        for key, _tier in _TIERS:
            for f in r[key]:
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
            "snippet": text[b["start"]:b["end"]].strip()[:100],
        })
        if "pack_findings" in r:
            out[-1]["pack_findings"] = r["pack_findings"]
    return out
