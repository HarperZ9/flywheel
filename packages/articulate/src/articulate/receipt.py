#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.receipt -- re-derivable verdicts.

A receipt records a detection result together with the exact text hash and
ruleset fingerprint that produced it. Anyone can replay it: recompute the
findings on the same text under the same ruleset and confirm they match, without
trusting whoever issued the receipt first. The verdict uses a closed lattice,
Match / Drift / Unverifiable, and there is deliberately no Trusted or Approved
value: the receipt certifies re-derivability, never authority.

  Match         same text, same ruleset, identical findings and gate.
  Drift         same text and ruleset, but the re-derived findings differ
                (the detector code changed outside the pinned patterns, or the
                receipt was altered).
  Unverifiable  the ruleset changed, the text does not match the receipt's hash,
                or the receipt schema is unknown. Re-derivation cannot be done,
                so nothing is asserted.

A content-free AUDIT receipt (schema `articulate/receipt/audit/v1`) keeps no verbatim
document text: it drops the per-finding `match` substring and the exact start/end/col
offsets, keeping only the rule id, tier, category, and line. A team retains and
replays such a record without storing the sensitive text. It is content-free, never
information-free: which rules fired and roughly where (line) remain, which for a
closed-vocabulary rule narrows the flagged token to that rule's small, public
candidate set. The "hash" mode keeps a sha256 of the match for an equality check
against a known string; it is not confidentiality, because most rules draw from a
public closed vocabulary a holder can enumerate and hash. Use "drop" when the flagged
word must stay secret.

A receipt made under a project config (articulate.project) embeds the
terminology and pack options as `project_rules` with their hash
`project_rules_sha256`, so anyone can replay it with no access to the project.
A payload that no longer matches its hash reads Unverifiable.

A receipt under a domain profile (articulate.domains) or project rules also
records `extension_fingerprint`, a hash of the rule packs and terminology rule
format that ran outside the detector.
Verify re-derives under the same packs, and reads Unverifiable when that hash
no longer matches, so a pack change never shows as a silent mismatch. A receipt
with no rule packs carries no such field and is unchanged.

Standard library only; no network.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from . import calibration, checkext, detector, domains, mdstructure, profiles, project, rules_ext

SCHEMA = "articulate/receipt/v1"
AUDIT_SCHEMA = "articulate/receipt/audit/v1"


def _sha256(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def text_sha256(text: str) -> str:
    """The receipt's canonical text hash, so a caller can tell a source changed
    since screening apart from a re-derivation result."""
    return _sha256(text)


def _pkg_version() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return "0.0.0"


def _normalize(result, redaction=None) -> list:
    """The verified core of a receipt: findings reduced to what a replay must
    reproduce, ordered so comparison is stable. A full receipt (redaction None)
    keeps the verbatim `match` and exact offsets. A content-free receipt ("drop" or
    "hash") keeps only rule_id, tier, category, and line: the exact offsets are
    dropped too, because `end - start` is the match length and, with a rule_id that
    names the rule's small candidate set, that length reconstructs the flagged word.
    "hash" additionally keeps a sha256 of the match, which is an equality fingerprint,
    not confidentiality (see the module docstring). Verify projects the re-derived
    findings to the receipt's redaction mode, so `match` and offsets are never part of
    the Match/Drift decision for a content-free receipt."""
    content_free = redaction in ("drop", "hash")
    out = []
    for f in result["high"] + result["medium"] + result["low"]:
        rec = {"rule_id": f["rule_id"], "tier": f["tier"], "category": f["category"],
               "line": f["line"]}
        if not content_free:
            rec["col"] = f["col"]
            rec["start"] = f["start"]
            rec["end"] = f["end"]
            rec["match"] = f["match"]
        elif redaction == "hash":
            rec["match_sha256"] = _sha256(f["match"])
        out.append(rec)
    out.sort(key=lambda x: (x["line"], x.get("start", 0), x["rule_id"]))
    return out


def _block_receipt(text, prof, structure=True, calibration=True) -> list:
    """Per-span (per-paragraph) verdicts for the receipt: which block is flagged,
    its line range, its own text hash, and its localized texture. This is what
    makes the receipt reportable per span, beyond the whole-document verdict."""
    out = []
    for b in checkext.analyze_blocks(text, profile=prof, structure=structure,
                                     calibration=calibration):
        out.append({
            "index": b["index"],
            "start_line": b["start_line"], "end_line": b["end_line"],
            "text_sha256": _sha256(text[b["start"]:b["end"]]),
            "gate": b["gate"], "clean": b["clean"], "verdict": b["verdict"],
            "texture_score": b["texture_score"], "elevated": b["elevated"],
            "counts": b["counts"],
        })
    return out


def make_receipt(text: str, profile_name: str = None, *, per_span: bool = False,
                 redact: str = None, reviewer: str = None,
                 created_at: str = None, config=None) -> dict:
    """Build a receipt. `redact` None gives the full content-bearing receipt;
    "drop" or "hash" gives a content-free audit receipt (schema audit/v1) that keeps
    no verbatim document text. The per-span blocks are already content-free.

    `created_at` (ISO-8601, defaults to now in UTC) and `reviewer` are the "who and
    when" envelope. They are issuance provenance, not part of the verified core, so
    verify never re-derives them and they never affect the Match/Drift decision."""
    if redact not in (None, "drop", "hash"):
        raise ValueError(f"redact must be None, 'drop', or 'hash'; got {redact!r}")
    pname = profile_name or profiles.DEFAULT
    rules = project.rules_payload(config)
    prof = project.apply_payload(domains.load_profile(pname), rules)
    r = checkext.check_text(text, profile=prof)
    content_free = redact in ("drop", "hash")
    rec = {
        "schema": AUDIT_SCHEMA if content_free else SCHEMA,
        "articulate_version": _pkg_version(),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "reviewer": reviewer,
        "ruleset_version": detector.ruleset_fingerprint(),
        "profile": pname,
        "text_sha256": _sha256(text),
        "gate": r["gate"],
        "clean": r["clean"],
        "verdict": r["verdict"],
        "sufficient": r["sufficient"],
        "texture_score": r["texture_score"],
        "counts": {"high": len(r["high"]), "medium": len(r["medium"]),
                   "low": len(r["low"])},
        "findings": _normalize(r, redact),
    }
    if content_free:
        rec["redaction"] = redact
    if rules:
        rec["project_rules"] = rules
        rec["project_rules_sha256"] = project.payload_sha256(rules)
    if rules_ext.active(prof):
        rec["extension_fingerprint"] = rules_ext.fingerprint()
    # Named only when the Markdown masks change this text, so a receipt for text
    # without that structure is the same as before the masks existed.
    if checkext.changes_text(text):
        rec["structure"] = checkext.STRUCTURE_VERSION
    # Named only when the calibration layer moved a finding in this text, so a
    # receipt for text it leaves alone is the same as before the layer existed.
    if "calibration" in r:
        rec["calibration"] = r["calibration"]
    if per_span:
        rec["blocks"] = _block_receipt(text, prof)
    return rec


def _extension_problem(receipt, prof):
    """Why the rule layer cannot be re-derived, or None when it can."""
    recorded = receipt.get("extension_fingerprint")
    if not rules_ext.active(prof):
        return "receipt records rule packs its profile does not run" if recorded else None
    current = rules_ext.fingerprint()
    if recorded != current:
        return (f"rule packs changed ({recorded} -> {current}); "
                f"cannot re-derive under different rule packs")
    return None


def _replay_profile(receipt, prof):
    """(profile with the embedded project rules applied, problem or None)."""
    rules = receipt.get("project_rules")
    if rules is not None:
        if receipt.get("project_rules_sha256") != project.payload_sha256(rules):
            return prof, "embedded project rules do not match their recorded hash"
        try:
            project.check_payload(rules)
        except project.ConfigError as e:
            return prof, f"embedded project rules are malformed: {e}"
        prof = project.apply_payload(prof, rules)
    return prof, _extension_problem(receipt, prof)


def verify_receipt(receipt: dict, text: str):
    """Replay a receipt against text. Returns (verdict, detail)."""
    if not isinstance(receipt, dict) or receipt.get("schema") not in (SCHEMA, AUDIT_SCHEMA):
        return "Unverifiable", "unknown or missing receipt schema"
    # The schema and redaction must be a consistent pair, so a full receipt cannot be
    # relabeled content-free (or the reverse) to smuggle a false claim past verify.
    schema, redaction = receipt.get("schema"), receipt.get("redaction")
    if schema == AUDIT_SCHEMA and redaction not in ("drop", "hash"):
        return "Unverifiable", "audit-schema receipt has no valid redaction mode"
    if schema == SCHEMA and redaction is not None:
        return "Unverifiable", "full-schema receipt declares a redaction mode"
    # A content-free receipt must carry no verbatim text in its own payload.
    if redaction in ("drop", "hash") and any("match" in f for f in receipt.get("findings", [])):
        return "Unverifiable", "content-free receipt carries a verbatim match field"
    current = detector.ruleset_fingerprint()
    if receipt.get("ruleset_version") != current:
        return ("Unverifiable",
                f"ruleset changed ({receipt.get('ruleset_version')} -> {current}); "
                f"cannot re-derive under a different ruleset")
    if receipt.get("text_sha256") != _sha256(text):
        return "Unverifiable", "text does not match the receipt's text hash"
    pname = receipt.get("profile", profiles.DEFAULT)
    try:
        prof = domains.load_profile(pname)
    except profiles.ProfileError:
        return "Unverifiable", f"receipt names an unknown profile {pname!r}"
    prof, problem = _replay_profile(receipt, prof)
    if problem:
        return "Unverifiable", problem
    # A receipt without the field predates the Markdown masks, or its text has
    # none of that structure; either way the unmasked replay re-derives it.
    recorded = receipt.get("structure")
    if recorded is not None and recorded not in mdstructure.VERSIONS:
        return "Unverifiable", f"receipt names unknown structure masks {recorded!r}"
    structure = recorded if recorded is not None else False
    calib = receipt.get("calibration")
    if calib is not None and calib not in calibration.VERSIONS:
        return "Unverifiable", f"receipt names unknown calibration {calib!r}"
    calib = calib if calib is not None else False
    r = checkext.check_text(text, profile=prof, structure=structure, calibration=calib)
    # Project the re-derived findings to the receipt's redaction mode, so a
    # content-free receipt reads Match and `match`/offsets never drive the verdict.
    same = (_normalize(r, redaction) == receipt.get("findings")
            and r["gate"] == receipt.get("gate")
            and r["texture_score"] == receipt.get("texture_score"))
    if not same:
        return "Drift", "re-derived findings or verdict differ from the receipt"
    # Below the word floor a device-clean text with no findings has too little
    # signal to assert; the receipt abstains and makes no confident clean claim.
    if r["verdict"] == "unverifiable":
        return ("Unverifiable",
                f"below the {detector.MIN_WORDS_FOR_VERDICT}-word signal floor; "
                f"no confident clean verdict on this little text")
    # A per-span receipt also re-derives its per-block verdicts.
    if ("blocks" in receipt
            and _block_receipt(text, prof, structure, calib) != receipt["blocks"]):
        return "Drift", "re-derived per-span block verdicts differ from the receipt"
    n = len(r["high"]) + len(r["medium"]) + len(r["low"])
    span = f", {len(receipt['blocks'])} spans" if "blocks" in receipt else ""
    return "Match", f"re-derived {n} findings, gate {r['gate']}, texture {r['texture_score']}{span}"
