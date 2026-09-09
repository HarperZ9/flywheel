"""Declared credential slots surfaced by the native keychain UI."""
from __future__ import annotations

from collections.abc import Callable, Mapping

BULLETIN_CREDENTIAL_NAME = "BULLETIN_AGENT_JWK"

EXTRA_NATIVE_KEY_SLOTS = {
    BULLETIN_CREDENTIAL_NAME: {
        "purpose": "Bulletin Ed25519 signing identity JWK",
        "value": "JSON object with public and private Ed25519 JWK members",
    },
}


def generic_keychain_set_error(name: str) -> dict | None:
    """Reject native identity slots that need structured import/create guards."""
    if protected_keychain_name(name) == BULLETIN_CREDENTIAL_NAME:
        return {"error": {
            "code": "USE_BULLETIN_IDENTITY",
            "message": "use flywheel bulletin-identity for BULLETIN_AGENT_JWK",
        }}
    return None


def protected_keychain_name(name: str) -> str | None:
    """Canonical protected slot for a case-insensitive native keychain name."""
    folded = _fold_keychain_name(name)
    for candidate in EXTRA_NATIVE_KEY_SLOTS:
        if folded == _fold_keychain_name(candidate):
            return candidate
    return None


def declared_key_names(
        providers: Mapping[str, Mapping[str, object]] | None = None) -> tuple[str, ...]:
    """Return model-provider keys plus non-provider native credential slots."""
    if providers is None:
        try:
            from .endpoints import PROVIDERS as providers
        except Exception:
            providers = {}
    names = {
        str(spec.get("key", "")).strip()
        for spec in providers.values()
        if isinstance(spec, Mapping) and str(spec.get("key", "")).strip()
    }
    names.update(EXTRA_NATIVE_KEY_SLOTS)
    return tuple(sorted(names))


def keychain_entries(
        credential_source: Callable[[str], str],
        providers: Mapping[str, Mapping[str, object]] | None = None,
) -> list[dict[str, str]]:
    """Presence-only rows for the gateway; values never leave keychain callers."""
    return [
        {"name": name, "source": credential_source(name)}
        for name in declared_key_names(providers)
    ]


def _fold_keychain_name(name: str) -> str:
    return name.casefold()
