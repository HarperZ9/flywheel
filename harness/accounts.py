"""accounts.py -- more than one stored key per provider, by name.

A provider has one slot the backends read, `flywheel/<ENV_NAME>`. The active
account's key lives in that slot, so every reader keeps working unchanged and
a key stored before named accounts existed is the account called `default`
with nothing to migrate. An account that is not active is parked beside the
slot as `flywheel/<ENV_NAME>@<label>`. Switching parks the active key and moves
the chosen one into the slot.

Labels and the active label are kept in FLYWHEEL_HOME/accounts.json. That file
holds names only. A key is never written to it, returned by a listing, or put
in a message: every function here answers with labels and plain sentences.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

DEFAULT = "default"
PROVIDERS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
             "gemini": "GEMINI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
             "openrouter": "OPENROUTER_API_KEY"}
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}\Z")


class AccountsError(Exception):
    """A named-account request that cannot be carried out; the text is safe
    to print (it never contains a key)."""


class KeychainStore:
    """The OS credential store, looked up at call time so a test that swaps
    a keychain function swaps it here too."""

    def available(self) -> bool:
        from harness import keychain
        return keychain.keychain_available()

    def get(self, name: str) -> "str | None":
        from harness import keychain
        return keychain.keychain_get(name)

    def set(self, name: str, secret: str) -> dict:
        from harness import keychain
        return keychain.keychain_set(name, secret)

    def delete(self, name: str) -> dict:
        from harness import keychain
        return keychain.keychain_delete(name)


def index_path(environ=None) -> Path:
    from harness.lane_workdir import flywheel_home
    return flywheel_home(os.environ if environ is None else environ) / "accounts.json"


def label_error(label: str) -> "str | None":
    if not isinstance(label, str) or not _LABEL.match(label):
        return ("an account label is 1 to 32 characters: letters, digits, "
                "dot, dash or underscore, starting with a letter or digit")
    return None


def error_text(result) -> str:
    """The store's own reason from a set or delete result, or ''."""
    error = result.get("error") if isinstance(result, dict) else "no result"
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "error")
    return str(error or "")


def _env(provider: str) -> str:
    if provider not in PROVIDERS:
        raise AccountsError(f"unknown provider '{provider}'; known: "
                            f"{', '.join(sorted(PROVIDERS))}")
    return PROVIDERS[provider]


def _checked(provider: str, label: str) -> str:
    env = _env(provider)
    problem = label_error(label)
    if problem:
        raise AccountsError(problem)
    return env


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AccountsError(f"cannot read the account list at {path} "
                            f"({type(exc).__name__}); fix or remove that file") from exc
    providers = data.get("providers") if isinstance(data, dict) else None
    return providers if isinstance(providers, dict) else {}


def _save(path: Path, providers: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"version": 1, "providers": providers},
                                  indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        raise AccountsError(f"cannot write the account list at {path} "
                            f"({type(exc).__name__})") from exc


def _view(providers: dict, provider: str, env: str, store) -> dict:
    """Labels and the active label for one provider. A key sitting in the slot
    with no active label recorded is the `default` account."""
    raw = providers.get(provider) if isinstance(providers.get(provider), dict) else {}
    labels = [x for x in raw.get("labels", []) if isinstance(x, str) and not label_error(x)]
    active = raw.get("active") if raw.get("active") in labels else None
    if active is None and store.get(env):
        active = DEFAULT
        if DEFAULT not in labels:
            labels.insert(0, DEFAULT)
    return {"labels": labels, "active": active}


def list_accounts(store=None, path=None, environ=None) -> list:
    """One row per provider: labels, the active label, and whether the
    environment variable is set (it wins over every stored account)."""
    store = store or KeychainStore()
    environ = os.environ if environ is None else environ
    providers = _load(path or index_path(environ))
    rows = []
    for provider, env in PROVIDERS.items():
        view = _view(providers, provider, env, store)
        rows.append({"provider": provider, "env": env, "labels": view["labels"],
                     "active": view["active"], "env_override": bool(environ.get(env))})
    return rows


def add_account(provider: str, label: str, secret: str, store=None, path=None) -> dict:
    """Store `secret` as the account `label`. It becomes the active account
    when the provider has none, or when `label` is already the active one."""
    env = _checked(provider, label)
    store, path = store or KeychainStore(), path or index_path()
    providers = _load(path)
    view = _view(providers, provider, env, store)
    becomes_active = view["active"] in (None, label)
    result = store.set(env if becomes_active else f"{env}@{label}", secret)
    if error_text(result):
        raise AccountsError(f"could not store the key: {error_text(result)}")
    if label not in view["labels"]:
        view["labels"].append(label)
    if becomes_active:
        view["active"] = label
    providers[provider] = view
    _save(path, providers)
    return {"provider": provider, "label": label, "env": env, "active": becomes_active}


def use_account(provider: str, label: str, store=None, path=None) -> dict:
    """Make `label` the account the backends read."""
    env = _checked(provider, label)
    store, path = store or KeychainStore(), path or index_path()
    providers = _load(path)
    view = _view(providers, provider, env, store)
    if label not in view["labels"]:
        raise AccountsError(f"no account '{label}' for {provider}; add it with "
                            f"`flywheel setup --provider {provider} --account {label}`")
    if view["active"] == label:
        return {"provider": provider, "label": label, "changed": False, "note": ""}
    chosen = store.get(f"{env}@{label}")
    if not chosen:
        raise AccountsError(f"the account '{label}' for {provider} has no stored key; "
                            f"store it again with `flywheel setup --provider {provider} "
                            f"--account {label}`")
    current = store.get(env) if view["active"] else None
    if current and error_text(store.set(f"{env}@{view['active']}", current)):
        raise AccountsError(f"could not keep the '{view['active']}' key aside; nothing changed")
    if error_text(store.set(env, chosen)):
        raise AccountsError("could not write the active key; nothing changed")
    leftover = error_text(store.delete(f"{env}@{label}"))
    view["active"] = label
    providers[provider] = view
    _save(path, providers)
    note = "a spare copy of this key could not be cleared from the store" if leftover else ""
    return {"provider": provider, "label": label, "changed": True, "note": note}


def remove_account(provider: str, label: str, store=None, path=None) -> dict:
    """Delete the account's key and forget its label."""
    env = _checked(provider, label)
    store, path = store or KeychainStore(), path or index_path()
    providers = _load(path)
    view = _view(providers, provider, env, store)
    if label not in view["labels"]:
        raise AccountsError(f"no account '{label}' for {provider}")
    was_active = view["active"] == label
    missing = error_text(store.delete(env if was_active else f"{env}@{label}"))
    view["labels"].remove(label)
    if was_active:
        view["active"] = None
    providers[provider] = view
    _save(path, providers)
    return {"provider": provider, "label": label, "was_active": was_active,
            "remaining": list(view["labels"]), "key_found": not missing}
