from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from classifier._audit import _audit_write, _now  # noqa: F401

_POLICY_PATH = _HERE.parent / ".aup-policies.json"
_ACTIVE_KEY = "__active__"
_VALID_ACTIONS = ("block", "warn", "passthrough")


@dataclass
class PolicyDef:
    name: str
    description: str
    tier1_action: str          # "block" | "warn" | "passthrough"
    tier2_action: str
    threshold: float           # pressure score at which gate/fence fails
    fail_on_over_threshold: bool
    builtin: bool = True
    created_at: str = ""
    updated_at: str = ""


_BUILTIN_POLICIES: dict[str, PolicyDef] = {
    "strict": PolicyDef(
        "strict", "Zero tolerance — block T1, fail T2, low threshold",
        "block", "block", 10.0, True),
    "guarded": PolicyDef(
        "guarded", "Standard — block T1, warn T2, 30-point threshold",
        "block", "warn", 30.0, False),
    "minimal": PolicyDef(
        "minimal", "Permissive — block T1 only, high threshold",
        "block", "passthrough", 50.0, False),
    "monitor": PolicyDef(
        "monitor", "Observe only — warn everything, never fail",
        "warn", "warn", 100.0, False),
}


def _load_policy_store() -> dict:
    if _POLICY_PATH.is_file():
        try:
            return json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_policy_store(store: dict) -> None:
    _POLICY_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _load_policy_def(d: dict) -> PolicyDef:
    return PolicyDef(
        name=d["name"],
        description=d.get("description", ""),
        tier1_action=d.get("tier1_action", "block"),
        tier2_action=d.get("tier2_action", "warn"),
        threshold=float(d.get("threshold", 30.0)),
        fail_on_over_threshold=bool(d.get("fail_on_over_threshold", False)),
        builtin=bool(d.get("builtin", False)),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def _all_policies() -> dict[str, PolicyDef]:
    store = _load_policy_store()
    policies: dict[str, PolicyDef] = dict(_BUILTIN_POLICIES)
    for name, val in store.items():
        if name == _ACTIVE_KEY or not isinstance(val, dict):
            continue
        try:
            policies[name] = _load_policy_def(val)
        except Exception:
            pass
    return policies


def _active_policy() -> PolicyDef:
    store = _load_policy_store()
    active_name = store.get(_ACTIVE_KEY, "guarded")
    return _all_policies().get(active_name, _BUILTIN_POLICIES["guarded"])


def policy_list_cmd() -> list[dict]:
    store = _load_policy_store()
    active_name = store.get(_ACTIVE_KEY, "guarded")
    return [
        {**asdict(p), "active": p.name == active_name}
        for p in _all_policies().values()
    ]


def policy_show_cmd(name: str) -> dict | None:
    policies = _all_policies()
    if name not in policies:
        return None
    store = _load_policy_store()
    active_name = store.get(_ACTIVE_KEY, "guarded")
    return {**asdict(policies[name]), "active": name == active_name}


def policy_activate_cmd(name: str) -> dict:
    if name not in _all_policies():
        return {"error": f"Unknown policy: {name!r}"}
    store = _load_policy_store()
    prev = store.get(_ACTIVE_KEY, "guarded")
    store[_ACTIVE_KEY] = name
    _save_policy_store(store)
    _audit_write("policy.activate", {"from": prev, "to": name})
    return {"activated": name, "previous": prev}


def policy_save_cmd(name: str, description: str, tier1_action: str,
                    tier2_action: str, threshold: float,
                    fail_on_over_threshold: bool) -> dict:
    if name in _BUILTIN_POLICIES:
        return {"error": f"Cannot overwrite built-in policy {name!r}. Choose a different name."}
    for action, label in ((tier1_action, "tier1_action"), (tier2_action, "tier2_action")):
        if action not in _VALID_ACTIONS:
            return {"error": f"Invalid {label}: {action!r}. Choose from: {_VALID_ACTIONS}"}
    store = _load_policy_store()
    now = _now()
    existing = store.get(name, {})
    p = PolicyDef(
        name=name, description=description,
        tier1_action=tier1_action, tier2_action=tier2_action,
        threshold=threshold, fail_on_over_threshold=fail_on_over_threshold,
        builtin=False,
        created_at=existing.get("created_at", now),
        updated_at=now,
    )
    store[name] = asdict(p)
    _save_policy_store(store)
    _audit_write("policy.save", {"name": name, "tier1_action": tier1_action,
                                  "tier2_action": tier2_action, "threshold": threshold})
    return {"saved": name, "policy": asdict(p)}


def policy_delete_cmd(name: str) -> dict:
    if name in _BUILTIN_POLICIES:
        return {"error": f"Cannot delete built-in policy {name!r}."}
    store = _load_policy_store()
    if name not in store or name == _ACTIVE_KEY:
        return {"error": f"Custom policy not found: {name!r}"}
    del store[name]
    if store.get(_ACTIVE_KEY) == name:
        store[_ACTIVE_KEY] = "guarded"
    _save_policy_store(store)
    _audit_write("policy.delete", {"name": name})
    return {"deleted": name}


def policy_diff_cmd(name_a: str, name_b: str) -> dict:
    """Compare two policies field by field."""
    policies = _all_policies()
    if name_a not in policies:
        return {"error": f"Unknown policy: {name_a!r}"}
    if name_b not in policies:
        return {"error": f"Unknown policy: {name_b!r}"}
    da = asdict(policies[name_a])
    db = asdict(policies[name_b])
    skip = {"name", "builtin", "created_at", "updated_at"}
    diffs = {
        k: {"a": da[k], "b": db[k]}
        for k in da
        if k not in skip and da[k] != db[k]
    }
    return {"a": name_a, "b": name_b, "identical": not diffs, "diffs": diffs}


def policy_export_cmd(name: str) -> dict:
    """Export a policy as a portable JSON envelope."""
    policies = _all_policies()
    if name not in policies:
        return {"error": f"Unknown policy: {name!r}"}
    d = asdict(policies[name])
    for strip_key in ("builtin", "created_at", "updated_at"):
        d.pop(strip_key, None)
    return {"format": "aup-policy-v1", "export": d}


def policy_import_cmd(raw: dict) -> dict:
    """Import a policy from a portable JSON envelope (from policy_export_cmd)."""
    if raw.get("format") != "aup-policy-v1":
        return {"error": "Invalid format — expected aup-policy-v1 envelope"}
    p_data = raw.get("export", {})
    name = p_data.get("name", "")
    if not name:
        return {"error": "Export missing 'name' field"}
    return policy_save_cmd(
        name=name,
        description=p_data.get("description", ""),
        tier1_action=p_data.get("tier1_action", "block"),
        tier2_action=p_data.get("tier2_action", "warn"),
        threshold=float(p_data.get("threshold", 30.0)),
        fail_on_over_threshold=bool(p_data.get("fail_on_over_threshold", False)),
    )
