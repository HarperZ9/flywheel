"""oauth_service.py -- the sign-in seam shaped for a GUI, not a terminal.

oauth_signin.py is written for a console: the PKCE flow blocks until the
browser comes back, and the guided flow reads a hidden paste from stdin.
Neither fits an HTTP request. This module adapts both without loosening a
single rule:

  - a PKCE sign-in runs on a background thread, so the request returns at
    once and the UI polls the roster for the outcome,
  - a guided sign-in returns its numbered steps as data; the surface shows
    them, takes the paste in its own obscured field, and posts the value
    back, which lands in the same credential store,
  - a registered provider returns its refusal, unchanged.

The redaction discipline is unchanged and load-bearing: a token value is
accepted as input and handed to the credential store, and never appears in a
roster, a job record, a log, or an error.
"""
from __future__ import annotations

import threading
from typing import Optional

from . import keychain, oauth_signin
from .oauth_profiles import PROFILES

_LOCK = threading.Lock()
_JOBS: dict = {}          # provider -> {"state": ..., "error": ..., "at": ...}


def _set_job(provider: str, state: str, error: Optional[str] = None) -> None:
    with _LOCK:
        record = {"state": state}
        if error:
            record["error"] = error
        _JOBS[provider] = record


def _job(provider: str) -> dict:
    with _LOCK:
        return dict(_JOBS.get(provider) or {})


def auth_rows() -> dict:
    """The roster the surface renders: presence, source, terms, and whatever
    the last sign-in attempt did. Labels only; never a value."""
    rows = []
    for row in oauth_signin.status():
        job = _job(row["provider"])
        rows.append({**row,
                     "kind_label": {"pkce": "browser sign-in",
                                    "guided-cli": "provider tool",
                                    "registered": "needs registration"}
                     .get(row["kind"], row["kind"]),
                     "pending": job.get("state") == "running",
                     "last": job.get("state", ""),
                     "last_error": job.get("error", "")})
    return {"providers": rows,
            "credential_store": keychain.keychain_available(),
            "note": "Sign-in stores a token in the OS credential store under "
                    "the name the router reads. Values are never displayed."}


def begin(provider: str) -> dict:
    """Start a sign-in. A browser flow runs in the background and the caller
    polls; a guided flow returns steps for the surface to render; a
    registered provider returns its honest refusal."""
    profile = PROFILES.get(provider)
    if profile is None:
        return {"ok": False, "provider": provider,
                "error": f"unknown provider; known: {', '.join(sorted(PROFILES))}"}
    if not keychain.keychain_available():
        return {"ok": False, "provider": provider, "mode": "unavailable",
                "error": "no OS credential store on this platform, so a token "
                         "could not be kept. Use the provider's own tool and "
                         f"export {profile.keychain_name} instead."}
    if profile.kind == "guided-cli":
        return {"ok": True, "provider": provider, "mode": "guided",
                "steps": list(profile.guide),
                "keychain_name": profile.keychain_name,
                "sanction": profile.sanction}
    if profile.kind == "registered":
        result = oauth_signin.login(provider)   # refuses without a client id
        if not result.get("ok"):
            return {**result, "mode": "registered"}
        return {**result, "mode": "browser"}
    if _job(provider).get("state") == "running":
        return {"ok": True, "provider": provider, "mode": "browser",
                "note": "a sign-in is already running; finish it in the browser"}

    def _run():
        try:
            result = oauth_signin.login(provider)
            _set_job(provider, "done" if result.get("ok") else "failed",
                     result.get("error"))
        except Exception as exc:                 # never leak a body or value
            _set_job(provider, "failed", f"sign-in failed ({type(exc).__name__})")

    _set_job(provider, "running")
    threading.Thread(target=_run, daemon=True, name=f"signin-{provider}").start()
    return {"ok": True, "provider": provider, "mode": "browser",
            "note": "a browser window is opening; approve the sign-in there"}


def submit(provider: str, token: str) -> dict:
    """Store a token the surface collected in its own obscured field. Only a
    guided provider takes this path: a browser flow must not accept a pasted
    value it did not obtain itself."""
    profile = PROFILES.get(provider)
    if profile is None:
        return {"ok": False, "provider": provider, "error": "unknown provider"}
    if profile.kind != "guided-cli":
        return {"ok": False, "provider": provider,
                "error": f"{provider} signs in through its own flow, not a paste"}
    if not (token or "").strip():
        return {"ok": False, "provider": provider,
                "error": "nothing pasted; nothing stored"}
    result = oauth_signin._store(profile, token.strip())
    _set_job(provider, "done" if result.get("ok") else "failed",
             result.get("error"))
    return result


def sign_out(provider: str) -> dict:
    result = oauth_signin.logout(provider)
    with _LOCK:
        _JOBS.pop(provider, None)
    return result
