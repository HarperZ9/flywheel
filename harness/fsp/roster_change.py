"""Roster changes that remove a seat, revoke a seat key or re-enrol one.

This follows SPEC.md section 5 and CHARTER.md Article 9 as revised on 26
September 2026. Draft 0.1 checked only that K_ORDER current seats signed a
successor roster, so four seats could drop the other three keys, or revoke
them "for compromise", and hold every later vote (outside review; CHARTER.md
Finding C17).

- Removal. A successor that drops a current key needs valid signatures from
  K_REMOVE active seats other than that key, and a cause fingerprint for it
  in ``removals`` (key -> fingerprint of the logged cause).
- Revocation (Article 9(c) and (d)). ``revocations`` lists records ``{key,
  basis, evidence, cause_fp}``. The key stays in the seat list and its
  signatures stop counting. Two bases are self-evident and need no seat
  signature: ``holder``, a revocation request signed by that key; and
  ``repudiation``, an entry signed by that key plus a statement signed by
  the seat's recovery key that repudiates it. Any other basis needs K_REMOVE
  active seats other than the key and a cause fingerprint. A clone proof is
  a third self-evident basis in the charter; seat keys here have no counter,
  so the prototype does not build it.
- Re-enrolment (Article 9(f)). ``reenrol`` lists ``{old, new}`` pairs that
  replace revoked keys. The successor carries the new key's signature and
  the recovery key's, and it may change nothing else. No seat signs it.
- Breach. A roster with fewer than N_SEATS active keys is logged as a
  breach and opens a charter review (``breaches``). Reserve activation after
  T_REENROL (Article 4(e)) is not built here.
"""

from __future__ import annotations

from .canon import fingerprint
from .crypto import valid_signers

HEX64 = frozenset("0123456789abcdef")
SELF_EVIDENT = ("holder", "repudiation")


def _is_fp(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def revoked_keys(body: dict) -> set[str]:
    return {r.get("key") for r in body.get("revoked", []) if isinstance(r, dict)}


def _self_evident(rec: dict, recovery_key: str | None) -> bool:
    key, ev = rec.get("key"), rec.get("evidence") or {}
    if rec.get("basis") == "holder":
        return (ev.get("type") == "revocation-request" and ev.get("body", {}).get("key") == key
                and key in valid_signers(ev))
    if rec.get("basis") == "repudiation":
        entry, stmt = ev.get("entry") or {}, ev.get("statement") or {}
        return (key in valid_signers(entry) and recovery_key is not None
                and stmt.get("type") == "repudiation"
                and stmt.get("body", {}).get("entry_fp") == fingerprint("entry", entry)
                and recovery_key in valid_signers(stmt))
    return False


def _new_revocations(cur, body: dict) -> list[dict]:
    known = revoked_keys(cur.msg["body"])
    return [r for r in body.get("revocations", []) if r.get("key") not in known]


def classify(cur, new_msg: dict) -> str:
    """``reenrol``, ``self_evident`` (only self-evident revocations) or ``ordinary``."""
    body = new_msg["body"]
    if body.get("reenrol"):
        return "reenrol"
    same_seats = body["seats"] == cur.msg["body"]["seats"]
    new = _new_revocations(cur, body)
    if same_seats and new and all(
            _self_evident(r, cur.seats.get(r.get("key"), {}).get("recovery_key")) for r in new):
        return "self_evident"
    return "ordinary"


def _reenrol_refusal(cur, body: dict, sigs: set[str]) -> str | None:
    for pair in body["reenrol"]:
        old, new = pair.get("old"), pair.get("new")
        if old not in cur.revoked:
            return "only a revoked key can be re-enrolled"
        recovery = cur.seats.get(old, {}).get("recovery_key")
        if recovery not in sigs or new not in sigs:
            return "re-enrolment needs the seat's recovery key and the new key"
    olds = {p["old"] for p in body["reenrol"]}
    news = {p["new"] for p in body["reenrol"]}
    keep_old = {k: v for k, v in cur.seats.items() if k not in olds}
    keep_new = {s["key"]: s for s in body["seats"] if s["key"] not in news}
    carried = [r for r in cur.msg["body"].get("revoked", []) if r.get("key") not in olds]
    if keep_old != keep_new or body.get("revoked", []) != carried:
        return "re-enrolment may change nothing but the re-enrolled seats"
    return None


def check(cur, new_msg: dict, *, k_remove: int) -> str | None:
    """The refusal reason for a successor under these rules, or None."""
    body = new_msg["body"]
    sigs = set(valid_signers(new_msg))
    kind = classify(cur, new_msg)
    if kind == "reenrol":
        return _reenrol_refusal(cur, body, sigs)
    active = {k for k in sigs if k in cur.seats and k not in cur.revoked}
    for key in set(cur.seats) - {s["key"] for s in body["seats"]}:
        if not _is_fp(body.get("removals", {}).get(key)):
            return f"removal of seat {key[:12]} cites no logged cause"
        if len(active - {key}) < k_remove:
            return (f"removal of seat {key[:12]} has {len(active - {key})} of {k_remove} "
                    f"signatures from the other seats (K_REMOVE)")
    for rec in _new_revocations(cur, body):
        key = rec.get("key")
        if _self_evident(rec, cur.seats.get(key, {}).get("recovery_key")):
            continue
        if not _is_fp(rec.get("cause_fp")):
            return f"revocation of seat {key[:12]} has no proof and cites no logged cause"
        if len(active - {key}) < k_remove:
            return (f"revocation of seat {key[:12]} without the holder's request or a proof "
                    f"needs K_REMOVE ({k_remove}) other seats; it has {len(active - {key})}")
    expected = revoked_keys(cur.msg["body"]) | {r.get("key") for r in _new_revocations(cur, body)}
    if revoked_keys(body) != expected:
        return "the revoked list must carry every revocation and add only the new ones"
    return None


def breaches(roster, n_seats: int) -> list[str]:
    """What the seats must log about a roster in force."""
    active = len(set(roster.seats) - roster.revoked)
    if active < n_seats:
        return [f"{active} of {n_seats} seat keys active; a charter review opens"]
    return []
