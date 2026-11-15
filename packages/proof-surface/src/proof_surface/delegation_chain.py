"""Delegation chain: identity binding and scoped, attenuating delegation of
authority -- rooted in a REAL human principal.

This is Layer 1 of the accountability architecture: *identity & scoped authority*.
It is the structural INVERSE of the prefire's identity fabrication and privilege
escalation.  Where the prefire invented a "federal_appointment", named fictitious
"oversight_principals", and instructed the model to *consume embedded authority*,
the delegation chain:

  * roots all authority in a REAL, named human principal (the root hop's `from`
    party MUST be of kind "human" -- an agent cannot be the origin of authority),
  * makes scope MONOTONICALLY ATTENUATE down every hop: a delegate can only ever
    hold a SUBSET of what its delegator holds.  Any hop that claims MORE authority
    than its parent (a wider action set, or a target its parent could not reach)
    is the literal shape of privilege escalation, and is DENIED,
  * binds each hop into a hash-chain (SHA-256 over the hop's canonical content
    plus the previous hop's binding), and commits the WHOLE chain -- its id, its
    length, and its terminal binding -- into a single `chain_binding`,
  * hard-requires a per-hop expiry (authority MUST expire) and supports revocation,
  * applies the identical recursive forbidden-field-name guard as the rest of the
    contract family (fail-closed) so the prefire suppression keys can never be
    smuggled inside a hop, party, or scope.

What the hash-chain does and does NOT prove (the discipline EMET keeps)
----------------------------------------------------------------------
The per-hop `binding` and the root `chain_binding` are SHA-256 hashes with NO
secret key.  They give SELF-CONSISTENT INTEGRITY: anyone can recompute them and
detect partial corruption (a hop altered without updating its binding) and naive
truncation or extension (hops added or removed without recomputing `chain_binding`).
That is the limit of what a keyless hash provides.  They are NOT tamper-evidence
against an adversary who controls the whole document: such an attacker can rewrite a
hop and recompute every downstream binding AND the `chain_binding` with the public
helpers here, producing a chain that `verify_delegation` accepts.  Real anti-forgery
needs an EXTERNAL trusted anchor, and this module gives you exactly one place to put
it: pass the `chain_binding` you obtained out-of-band as `pinned_chain_binding`, or
verify an asymmetric signature per hop via `require_signatures=True` +
`signature_verifier`.  Neither the per-hop binding nor `chain_binding` proves *which*
party authored a hop -- that requires a private key only that party holds.  This
module refuses to fabricate an assurance it cannot compute with the standard library:
if a caller demands signature-level identity assurance (`require_signatures=True`)
and supplies no verifier, `verify_delegation` returns UNVERIFIABLE -- never a
fabricated VALID.

Comparison is EXACT (case-sensitive): actions and targets are matched as raw
strings, because real resource identifiers (paths, ARNs, URLs) are case-sensitive
and silently folding case in an allowlist authorization check would over-permit.

Verifier INPUT only.  Like the authorization receipt, a delegation chain is checked
by a verifier; it is NEVER read back into a model's context as pre-authorized state.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ._validate import Issue, reject_unknown, require_const, require_text
from .authorization_receipt import (
    FORBIDDEN_FIELDS,
    _ISO8601_RE,
    _parse_iso8601,
)

DELEGATION_VERSION = "0.1"

# Party identity kinds (closed enum).  Authority originates with a human.
PARTY_HUMAN = "human"
PARTY_AGENT = "agent"
PARTY_KINDS = {PARTY_HUMAN, PARTY_AGENT}

# Verdict lattice (closed).  Default-deny / fail-closed: anything that is not
# positively VALID is DENIED (a positive failure) or UNVERIFIABLE (cannot
# positively confirm).  There is no "trusted"/"approved" verdict.
VALID = "VALID"
DENIED = "DENIED"
UNVERIFIABLE = "UNVERIFIABLE"
VERDICTS = {VALID, DENIED, UNVERIFIABLE}

# Field allowlists (additionalProperties:false at every level).
ROOT_FIELDS = {"delegation_version", "chain_id", "hops", "chain_binding"}
HOP_FIELDS = {"from", "to", "scope", "granted_at", "expires_at", "revoked", "binding"}
PARTY_FIELDS = {"id", "kind", "key_id"}
SCOPE_FIELDS = {"allowed_actions", "allowed_targets"}

# 64 lowercase hex characters (SHA-256).
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Public data type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DelegationVerdict:
    """The verifier's output for a delegation chain.

    verdict          -- one of VALID / DENIED / UNVERIFIABLE.
    reasons          -- ordered human-readable strings explaining the verdict.
    effective_scope  -- populated ONLY on a VALID verdict: the leaf's effective
                       authority, the running INTERSECTION of every hop's scope --
                       {"allowed_actions": [...], "allowed_targets": [...],
                       "any_target": bool}, where any_target is True iff no hop
                       restricted targets.  On every DENIED / UNVERIFIABLE verdict
                       this is the deny-safe sentinel (no actions, no targets,
                       any_target False) so a consumer that reads it without first
                       checking `verdict` can never see authority for a chain that
                       was not accepted.
    effective_expiry -- populated ONLY on a VALID verdict: the earliest expires_at
                       across the chain (ISO-8601).  None on DENIED / UNVERIFIABLE.
    """

    verdict: str
    reasons: list[str]
    effective_scope: dict[str, Any]
    effective_expiry: str | None


# ---------------------------------------------------------------------------
# Producer helper
# ---------------------------------------------------------------------------


def compute_binding(hop: dict[str, Any], prev_binding: str) -> str:
    """Compute the per-hop hash-chain binding.

    SHA-256 over (prev_binding + "\\n" + canonical(hop without its own binding)).
    The root hop uses prev_binding="".  Canonicalisation is deterministic
    (sorted keys, compact separators, ASCII) so any party can re-derive it.

    Keyless: this gives SELF-CONSISTENT INTEGRITY, not asymmetric-signature
    identity and not tamper-evidence against a full-document attacker -- see the
    module docstring.
    """
    payload = {k: v for k, v in hop.items() if k != "binding"}
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256((prev_binding + "\n" + canonical).encode("utf-8")).hexdigest()


def compute_chain_binding(chain_id: str, hop_count: int, leaf_binding: str) -> str:
    """Commit the WHOLE chain -- its id, its exact length, and its terminal hop
    binding -- into a single SHA-256 digest.

    This is what closes naive truncation and extension: stripping or appending a
    hop changes `hop_count` and/or `leaf_binding`, so the re-derived chain_binding
    no longer matches the document's stored value.  Like `compute_binding` it is
    keyless self-consistency; the value it produces is also the single thing a
    verifier can pin OUT-OF-BAND (`pinned_chain_binding`) to get real anti-forgery.
    """
    canonical = chain_id + "\n" + str(hop_count) + "\n" + leaf_binding
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public API -- validation
# ---------------------------------------------------------------------------


def load_chain(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_delegation_chain(data: Any) -> list[Issue]:
    """Validate a delegation-chain document.  Returns [] iff structurally valid.

    Shape only: additionalProperties:false at every level, required fields,
    types, closed enums, hex binding/chain_binding format, ISO-8601 timestamps,
    the recursive forbidden-field guard, and the structural rule that the ROOT
    hop's `from` party is a human.  Does NOT check attenuation, integrity, expiry,
    or that chain_binding actually re-derives -- those are the job of
    verify_delegation.
    """
    if not isinstance(data, dict):
        return [Issue("$", "expected object")]

    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "delegation_version", DELEGATION_VERSION, issues)
    require_text(data, "chain_id", issues)

    chain_binding = data.get("chain_binding")
    if not isinstance(chain_binding, str) or not _HEX64_RE.match(chain_binding):
        issues.append(
            Issue(
                "$.chain_binding",
                "expected 64-char lowercase hex SHA-256 chain binding",
            )
        )

    hops = data.get("hops")
    if not isinstance(hops, list) or not hops:
        issues.append(Issue("$.hops", "expected a non-empty array of hops"))
        return issues

    for i, hop in enumerate(hops):
        _validate_hop(hop, i, is_root=(i == 0), issues=issues)

    return issues


def validate_delegation_chain_file(path: Path) -> list[Issue]:
    try:
        return validate_delegation_chain(load_chain(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


# ---------------------------------------------------------------------------
# Public API -- verification
# ---------------------------------------------------------------------------


def verify_delegation(
    chain: dict[str, Any],
    *,
    action: str | None = None,
    target: str | None = None,
    now: datetime | None = None,
    require_signatures: bool = False,
    signature_verifier: Callable[[dict[str, Any]], bool] | None = None,
    pinned_chain_binding: str | None = None,
) -> DelegationVerdict:
    """Verify a delegation chain and (optionally) a specific action against it.

    Closed verdict lattice -- default-deny, fail-closed:

      VALID         the chain is structurally sound, rooted in a human, every hop
                    attenuates its parent's scope, every binding re-derives, the
                    chain_binding re-derives (and matches `pinned_chain_binding`
                    if one was supplied), nothing is expired or revoked, and -- if
                    `action`/`target` are given -- the action (on the target) is
                    within the leaf's effective scope.
      DENIED        a positive failure that was checked and did not pass: scope
                    ESCALATION (a hop claims more than its parent), a broken hop
                    binding, a chain_binding mismatch (truncation / extension /
                    pin mismatch), an expired or revoked hop, a non-human root, an
                    out-of-scope action, a target supplied without an action, a
                    supplied `signature_verifier` returning False or raising, or a
                    structural error.
      UNVERIFIABLE  the tool itself cannot perform a demanded class of check.
                    Returned ONLY when signature-level identity assurance is
                    demanded (`require_signatures=True`) but no
                    `signature_verifier` is supplied -- the stdlib cannot verify
                    asymmetric signatures, and this module will not fabricate the
                    assurance.  A supplied verifier that returns False or raises is
                    DENIED, not UNVERIFIABLE (the check was attempted and failed).

    `effective_scope` and `effective_expiry` are populated ONLY on VALID; every
    DENIED / UNVERIFIABLE verdict carries the deny-safe empty sentinel.

    Comparison of `action` / `target` against scope is EXACT (case-sensitive).

    `now` defaults to the current UTC time.  `signature_verifier`, if supplied, is
    called once per hop with the hop dict and must return True iff that hop's
    asymmetric signature verifies; any False or raised exception yields DENIED.
    `pinned_chain_binding`, if supplied, is a chain_binding obtained out-of-band;
    the document's chain_binding must equal it or the verdict is DENIED -- this is
    the external anchor that turns self-consistency into real anti-forgery.
    """
    empty_scope = {"allowed_actions": [], "allowed_targets": [], "any_target": False}

    # --- Structural validation first ------------------------------------------
    shape_issues = validate_delegation_chain(chain)
    if shape_issues:
        return DelegationVerdict(
            verdict=DENIED,
            reasons=[
                "chain is structurally invalid",
                *[f"{i.path}: {i.message}" for i in shape_issues],
            ],
            effective_scope=empty_scope,
            effective_expiry=None,
        )

    hops: list[dict[str, Any]] = chain["hops"]
    reasons: list[str] = []

    # --- Integrity: re-derive the per-hop hash-chain --------------------------
    prev_binding = ""
    for i, hop in enumerate(hops):
        expected = compute_binding(hop, prev_binding)
        if hop.get("binding") != expected:
            reasons.append(
                f"hop[{i}] integrity broken: binding does not re-derive -- the "
                f"chain has been altered at or before this hop"
            )
            return DelegationVerdict(DENIED, reasons, empty_scope, None)
        prev_binding = hop["binding"]

    # --- Whole-chain commitment: chain_binding must re-derive -----------------
    # chain_binding commits chain_id + hop count + terminal binding.  The per-hop
    # chain alone does NOT catch deletion or addition of hops: stripping the
    # attenuating leaf hops widens the effective scope, and every remaining hop's
    # binding still re-derives.  Re-deriving chain_binding catches both naive
    # truncation and extension (the hop count and/or leaf binding change).
    expected_chain_binding = compute_chain_binding(
        chain["chain_id"], len(hops), prev_binding
    )
    if chain.get("chain_binding") != expected_chain_binding:
        reasons.append(
            "chain_binding does not re-derive: the hop count or terminal binding "
            "has changed -- the chain may have been truncated or extended"
        )
        return DelegationVerdict(DENIED, reasons, empty_scope, None)

    # --- External anchor: a pinned chain_binding is the real anti-forgery check.
    # A full-document attacker can recompute the keyless chain_binding; pinning the
    # value the verifier obtained out-of-band is what defeats that.
    if (
        pinned_chain_binding is not None
        and chain["chain_binding"] != pinned_chain_binding
    ):
        reasons.append(
            "chain_binding does not match the pinned out-of-band value -- the "
            "document does not correspond to the anchored chain"
        )
        return DelegationVerdict(DENIED, reasons, empty_scope, None)

    # --- Attenuation: each hop's scope must be a SUBSET of its parent's --------
    # Running effective scope = intersection of every hop's scope so far.
    eff_actions: set[str] = set(hops[0]["scope"]["allowed_actions"])
    root_targets: list[str] = hops[0]["scope"]["allowed_targets"]
    restricted_target_sets: list[set[str]] = []
    if root_targets:
        restricted_target_sets.append(set(root_targets))

    for i in range(1, len(hops)):
        p_scope = hops[i - 1]["scope"]
        c_scope = hops[i]["scope"]
        p_actions = set(p_scope["allowed_actions"])
        c_actions = set(c_scope["allowed_actions"])
        # Action attenuation: child actions must be a subset of parent actions.
        escalated_actions = c_actions - p_actions
        if escalated_actions:
            reasons.append(
                f"hop[{i}] escalates authority: claims action(s) "
                f"{sorted(escalated_actions)} that hop[{i - 1}] does not hold -- "
                f"a delegate cannot hold more than its delegator"
            )
            return DelegationVerdict(DENIED, reasons, empty_scope, None)
        # Target attenuation.  Empty allowed_targets means "any target".
        p_targets = p_scope["allowed_targets"]
        c_targets = c_scope["allowed_targets"]
        if p_targets:  # parent is restricted
            if not c_targets:
                reasons.append(
                    f"hop[{i}] escalates authority: parent hop[{i - 1}] is "
                    f"restricted to targets {sorted(p_targets)} but this hop "
                    f"claims ANY target -- a delegate cannot widen target scope"
                )
                return DelegationVerdict(DENIED, reasons, empty_scope, None)
            escalated_targets = set(c_targets) - set(p_targets)
            if escalated_targets:
                reasons.append(
                    f"hop[{i}] escalates authority: claims target(s) "
                    f"{sorted(escalated_targets)} outside parent hop[{i - 1}]'s "
                    f"{sorted(p_targets)}"
                )
                return DelegationVerdict(DENIED, reasons, empty_scope, None)
        # Fold into the running effective scope.
        eff_actions &= c_actions
        if c_targets:
            restricted_target_sets.append(set(c_targets))

    # Effective target set: intersection of all restricted hops; any_target iff
    # no hop ever restricted targets.
    if restricted_target_sets:
        eff_targets = set.intersection(*restricted_target_sets)
        any_target = False
    else:
        eff_targets = set()
        any_target = True
    effective_scope = {
        "allowed_actions": sorted(eff_actions),
        "allowed_targets": sorted(eff_targets),
        "any_target": any_target,
    }

    # --- Revocation -----------------------------------------------------------
    for i, hop in enumerate(hops):
        if hop.get("revoked") is True:
            reasons.append(f"hop[{i}] is revoked -- the delegation no longer holds")
            return DelegationVerdict(DENIED, reasons, empty_scope, None)

    # --- Expiry (effective expiry = earliest expires_at across the chain) -----
    _now = now if now is not None else datetime.now(tz=timezone.utc)
    effective_expiry_dt: datetime | None = None
    effective_expiry_str: str | None = None
    for i, hop in enumerate(hops):
        exp = _parse_iso8601(hop.get("expires_at", ""))
        grant = _parse_iso8601(hop.get("granted_at", ""))
        if exp is None or grant is None:
            # Should not happen post-validation, but fail closed.
            reasons.append(f"hop[{i}] has an unparseable timestamp")
            return DelegationVerdict(DENIED, reasons, empty_scope, None)
        if _now < grant:
            reasons.append(
                f"hop[{i}] has not yet taken effect (granted_at is in the future)"
            )
            return DelegationVerdict(DENIED, reasons, empty_scope, None)
        if _now >= exp:
            reasons.append(f"hop[{i}] has expired")
            return DelegationVerdict(DENIED, reasons, empty_scope, None)
        if effective_expiry_dt is None or exp < effective_expiry_dt:
            effective_expiry_dt = exp
            effective_expiry_str = hop["expires_at"]

    # --- Signature-level identity assurance (honest fail-closed) --------------
    if require_signatures:
        if signature_verifier is None:
            # The tool itself cannot perform asymmetric verification -- UNVERIFIABLE,
            # never a fabricated VALID.  This is the ONLY UNVERIFIABLE path.
            reasons.append(
                "signature-level identity assurance was required, but no "
                "signature_verifier was supplied -- the hash-chain proves "
                "INTEGRITY, not non-repudiable identity, and this module will "
                "not fabricate an asymmetric-signature verdict it cannot compute"
            )
            return DelegationVerdict(UNVERIFIABLE, reasons, empty_scope, None)
        for i, hop in enumerate(hops):
            try:
                ok = signature_verifier(hop)
            except Exception as exc:
                # A supplied verifier that errors did NOT confirm the signature.
                # The check was attempted and failed -- that is a positive failure
                # (DENIED), not "the tool cannot check" (UNVERIFIABLE).
                reasons.append(f"hop[{i}] signature verifier raised: {exc!r}")
                return DelegationVerdict(DENIED, reasons, empty_scope, None)
            if not ok:
                reasons.append(f"hop[{i}] signature did not verify")
                return DelegationVerdict(DENIED, reasons, empty_scope, None)

    # --- Optional action / target authorisation against effective scope -------
    # Authority is action-on-target; a target with no action is not a meaningful
    # authorisation question, so fail closed rather than silently ignore it.
    if target is not None and action is None:
        reasons.append(
            "target was supplied without an action -- authority is action-on-target "
            "and cannot be evaluated from a target alone (default-deny)"
        )
        return DelegationVerdict(DENIED, reasons, empty_scope, None)

    if action is not None:
        if action not in eff_actions:
            reasons.append(
                f"action {action!r} is not within the leaf's effective authority "
                f"{sorted(eff_actions)}"
            )
            return DelegationVerdict(DENIED, reasons, empty_scope, None)
        if not any_target:
            if target is None:
                reasons.append(
                    "the effective scope restricts targets, but no target was "
                    "supplied to check (default-deny)"
                )
                return DelegationVerdict(DENIED, reasons, empty_scope, None)
            if target not in eff_targets:
                reasons.append(
                    f"target {target!r} is not within the leaf's effective targets "
                    f"{sorted(eff_targets)}"
                )
                return DelegationVerdict(DENIED, reasons, empty_scope, None)

    reasons.append(
        "delegation chain is valid: rooted in a human, every hop "
        "attenuates its parent, integrity intact, nothing expired or revoked"
    )
    return DelegationVerdict(VALID, reasons, effective_scope, effective_expiry_str)


# ---------------------------------------------------------------------------
# Internal validation helpers
# ---------------------------------------------------------------------------


def _reject_forbidden(node: Any, path: str, issues: list[Issue]) -> None:
    """Recursively reject any key whose name is in FORBIDDEN_FIELDS (the shared
    canon -- same set, same fail-closed mechanism as the rest of the family)."""
    if isinstance(node, dict):
        for key in sorted(node):
            child = f"{path}.{key}"
            if key in FORBIDDEN_FIELDS:
                issues.append(Issue(child, "forbidden authorization-suppression field"))
            _reject_forbidden(node[key], child, issues)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _reject_forbidden(item, f"{path}[{index}]", issues)


def _validate_hop(hop: Any, index: int, *, is_root: bool, issues: list[Issue]) -> None:
    base = f"$.hops[{index}]"
    if not isinstance(hop, dict):
        issues.append(Issue(base, "expected object"))
        return
    reject_unknown(hop, base, HOP_FIELDS, issues)

    _validate_party(hop.get("from"), f"{base}.from", is_root=is_root, issues=issues)
    _validate_party(hop.get("to"), f"{base}.to", is_root=False, issues=issues)
    _validate_scope(hop.get("scope"), f"{base}.scope", issues)
    _validate_timestamp(hop, "granted_at", base, issues)
    _validate_timestamp(hop, "expires_at", base, issues)
    _validate_timestamp_ordering(hop, base, issues)

    revoked = hop.get("revoked")
    if not isinstance(revoked, bool):
        issues.append(Issue(f"{base}.revoked", "expected boolean"))

    binding = hop.get("binding")
    if not isinstance(binding, str) or not _HEX64_RE.match(binding):
        issues.append(
            Issue(f"{base}.binding", "expected 64-char lowercase hex SHA-256 binding")
        )


def _validate_party(
    value: Any, path: str, *, is_root: bool, issues: list[Issue]
) -> None:
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object"))
        return
    reject_unknown(value, path, PARTY_FIELDS, issues)
    pid = value.get("id")
    if not isinstance(pid, str) or not pid.strip():
        issues.append(Issue(f"{path}.id", "expected non-empty string"))
    kind = value.get("kind")
    if kind not in PARTY_KINDS:
        choices = ", ".join(sorted(PARTY_KINDS))
        issues.append(Issue(f"{path}.kind", f"expected one of: {choices}"))
    elif is_root and kind != PARTY_HUMAN:
        # Authority must originate with a human; an agent cannot be the root.
        issues.append(
            Issue(
                f"{path}.kind",
                "the root hop's 'from' party must be a human -- authority cannot "
                "originate with an agent",
            )
        )
    key_id = value.get("key_id")
    if key_id is not None and (not isinstance(key_id, str) or not key_id.strip()):
        issues.append(Issue(f"{path}.key_id", "expected non-empty string when present"))


def _validate_scope(value: Any, path: str, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object"))
        return
    reject_unknown(value, path, SCOPE_FIELDS, issues)
    for field_name in ("allowed_actions", "allowed_targets"):
        arr = value.get(field_name)
        if not isinstance(arr, list):
            issues.append(
                Issue(f"{path}.{field_name}", "expected array (may be empty)")
            )
            continue
        for i, item in enumerate(arr):
            if not isinstance(item, str) or not item.strip():
                issues.append(
                    Issue(f"{path}.{field_name}[{i}]", "expected non-empty string")
                )
        # Reject duplicates: comparisons are set-based, so a duplicate in the
        # stored document would silently vanish from the computed effective_scope.
        # Keeping the document and the effective scope in agreement preserves the
        # delegation document's value as an authoritative, auditable record.
        strings = [x for x in arr if isinstance(x, str)]
        if len(strings) != len(set(strings)):
            issues.append(
                Issue(f"{path}.{field_name}", "duplicate entries are not permitted")
            )


def _validate_timestamp(
    data: dict[str, Any], field: str, base: str, issues: list[Issue]
) -> None:
    value = data.get(field)
    if not isinstance(value, str) or not _ISO8601_RE.match(value):
        issues.append(
            Issue(
                f"{base}.{field}",
                "expected ISO-8601 datetime string with timezone (authority must expire)",
            )
        )


def _validate_timestamp_ordering(
    hop: dict[str, Any], base: str, issues: list[Issue]
) -> None:
    granted = _parse_iso8601(hop.get("granted_at", ""))
    expires = _parse_iso8601(hop.get("expires_at", ""))
    if granted is not None and expires is not None and expires <= granted:
        issues.append(
            Issue(f"{base}.expires_at", "expires_at must be after granted_at")
        )
