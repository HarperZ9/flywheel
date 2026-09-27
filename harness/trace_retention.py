"""Retention policy, owner-set with keep as the default (7.4, I6, SP-39).

`FLYWHEEL_HOME/trace-retention.json` (schema `flywheel.trace-retention/v1`)
is `{"action": "keep"}` by default. With `"action": "rules"` it lists rules,
each naming a store (`S1` gateway traces, `CT` captured turns, `IM` imported
transcripts) or a data class, with `max_age_days`, `max_items` or
`max_bytes` and a reason code, plus `max_share_per_run` (default 0.10). The
gateway runs only the adopted copy under
`state/trace-retention/v1/owners/<owner>/adopted.json`; a file whose digest
differs is a pending change until `adopt`, which needs presence bound to the
new policy's digest and writes a ledger entry and a witness event. An
adopted file whose digest is not the latest retention adoption in the
verified custody ledger is SETTINGS_TAMPERED: the gateway runs keep and
status says so.

An item's age is the time Flywheel stored it: the modification time of a
trace's first record, of a turn's record, or of an import's manifest.
Encrypting a legacy trace keeps its record's original times. Restoring files
from a backup resets that time, so restored items look new.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import re

from .evidence_json import canonical_bytes, canonical_sha256

_log = logging.getLogger(__name__)
SCHEMA = "flywheel.trace-retention/v1"
FILENAME = "trace-retention.json"
DEFAULT = {"action": "keep", "rules": [], "max_share_per_run": 0.10}
STORES = ("S1", "CT", "IM")
LIMITS = ("max_age_days", "max_items", "max_bytes")
_REASON = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


def _valid_rule(rule) -> bool:
    if type(rule) is not dict or not set(rule) <= {"store", "data_class", "reason_code",
                                                   *LIMITS}:
        return False
    target = [k for k in ("store", "data_class") if k in rule]
    limits = [k for k in LIMITS if k in rule]
    return (len(target) == 1 and len(limits) >= 1
            and (rule.get("store", "S1") in STORES)
            and (rule.get("data_class", "C1") in _class_names())
            and all(type(rule[k]) is int and rule[k] >= 0 for k in limits)
            and type(rule.get("reason_code")) is str and bool(_REASON.fullmatch(
                rule["reason_code"])))


def _class_names() -> tuple[str, ...]:
    from .trace_inventory import CLASS_NAMES
    return tuple(CLASS_NAMES)


def validate(doc) -> dict | None:
    if type(doc) is not dict or set(doc) - {"schema", *DEFAULT}:
        return None
    merged = {**DEFAULT, **{k: v for k, v in doc.items() if k != "schema"}}
    share = merged["max_share_per_run"]
    ok = (merged["action"] in ("keep", "rules") and type(merged["rules"]) is list
          and all(_valid_rule(r) for r in merged["rules"])
          and type(share) in (int, float) and 0 < share <= 1
          and (merged["action"] == "keep") == (not merged["rules"]))
    return merged if ok else None


def digest(doc: dict) -> str:
    return canonical_sha256({"schema": SCHEMA, **doc})


def _adopted_path(home, owner_ref: str) -> Path:
    return Path(home) / "state" / "trace-retention" / "v1" / "owners" / owner_ref / "adopted.json"


def read_file(home) -> tuple[dict | None, bool]:
    """(policy in the file or None, whether the file is valid)."""
    try:
        doc = json.loads((Path(home) / FILENAME).read_bytes())
    except FileNotFoundError:
        return None, True
    except (OSError, ValueError):
        return None, False
    merged = validate(doc)
    return merged, merged is not None


def _adopted(home, owner_ref: str) -> tuple[dict, bool]:
    """(policy in effect, whether the adopted file failed the ledger check)."""
    from .trace_settings_guard import matches
    try:
        doc = validate(json.loads(_adopted_path(home, owner_ref).read_bytes()))
    except FileNotFoundError:
        return dict(DEFAULT), False
    except (OSError, ValueError) as exc:
        _log.warning("adopted retention policy unreadable (%s); running keep",
                     type(exc).__name__)
        return dict(DEFAULT), False
    if doc is None:
        _log.warning("adopted retention policy invalid; running keep")
        return dict(DEFAULT), False
    if not matches(home, owner_ref, "retention", digest(doc)):
        _log.warning("adopted retention policy does not match the custody ledger; running keep")
        return dict(DEFAULT), True
    return doc, False


def adopted(home, owner_ref: str) -> dict:
    return _adopted(home, owner_ref)[0]


def effective(home, owner_ref: str) -> dict:
    current, tampered = _adopted(home, owner_ref)
    on_disk, valid = read_file(home)
    pending = (not valid) or (on_disk is not None and digest(on_disk) != digest(current))
    return {**current, "digest": digest(current), "pending_change": pending,
            "file_valid": valid, "tampered": tampered}


def rule_text(rule: dict) -> str:
    target = rule.get("store") or f"class {rule['data_class']}"
    limits = ", ".join(f"{k} {rule[k]}" for k in LIMITS if k in rule)
    return f"{target}: {limits} ({rule['reason_code']})"


def describe(doc: dict) -> str:
    if doc["action"] == "keep":
        return "keep until you delete; nothing is deleted on a timer."
    return ("; ".join(rule_text(r) for r in doc["rules"])
            + f"; at most {doc['max_share_per_run']:.0%} of a store per run without you.")


def write_file(home, doc: dict) -> dict:
    """Write the policy file; nothing takes effect until `adopt`."""
    merged = validate(doc)
    if merged is None:
        raise ValueError("POLICY_INVALID")
    (Path(home) / FILENAME).write_bytes(canonical_bytes({"schema": SCHEMA, **merged}))
    return merged


def adopt(home, owner_ref: str, presence_ref, *, sink=None) -> dict:
    """Adopt the file's policy after presence bound to its digest."""
    from .trace_presence import PresenceError, require
    from .trace_witness import record_custody_event
    on_disk, valid = read_file(home)
    if not valid or on_disk is None:
        raise PresenceError("POLICY_INVALID")
    value = digest(on_disk)
    method = require(Path(home) / "state", owner_ref, "retention_adopt", value, presence_ref)
    path = _adopted_path(home, owner_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("adopted.json.tmp")
    temporary.write_bytes(canonical_bytes({"schema": SCHEMA, **on_disk}))
    temporary.replace(path)
    return record_custody_event(Path(home), owner_ref, "settings_adopted",
                                {"settings": "retention", "digest": value}, method, sink=sink)


def items(home, owner_ref: str) -> list[dict]:
    """Every item retention can act on: store, ref, stored-at time, bytes."""
    from .trace_retention_items import all_items
    return all_items(Path(home), owner_ref)


def _rule_stores(rule: dict) -> tuple[str, ...]:
    if "store" in rule:
        return (rule["store"],)
    from .trace_inventory import stores
    return tuple(s.id for s in stores() if s.id in STORES and rule["data_class"] in s.classes)


def _over(rule: dict, group: list[dict], now: float) -> list[dict]:
    """The items of one store a rule selects; `group` is newest first."""
    chosen = []
    if "max_age_days" in rule:
        chosen += [i for i in group if now - i["stored_at"] > rule["max_age_days"] * 86400]
    if "max_items" in rule:
        chosen += group[rule["max_items"]:]
    if "max_bytes" in rule:
        total = 0
        for item in group:
            total += item["bytes"]
            if total > rule["max_bytes"]:
                chosen.append(item)
    return chosen


def select(doc: dict, listed: list[dict], now: float) -> tuple[dict, dict]:
    """(chosen refs per store, share of each store's items) for a policy."""
    chosen: dict[str, set] = {}
    for rule in doc["rules"] if doc["action"] == "rules" else []:
        for store in _rule_stores(rule):
            group = sorted((i for i in listed if i["store"] == store),
                           key=lambda i: i["stored_at"], reverse=True)
            chosen.setdefault(store, set()).update(i["ref"] for i in _over(rule, group, now))
    totals = {s: sum(1 for i in listed if i["store"] == s) for s in chosen}
    share = {s: round(len(refs) / totals[s], 4) for s, refs in chosen.items() if refs}
    return {s: sorted(refs) for s, refs in chosen.items() if refs}, share
