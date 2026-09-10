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
  - a registered provider refuses until configured, then runs asynchronously.

The redaction discipline is unchanged and load-bearing: a token value is
accepted as input and handed to the credential store, and never appears in a
roster, a job record, a log, or an error.
"""
from __future__ import annotations

import threading
import urllib.parse
from typing import Optional

from . import keychain, oauth_signin
from .oauth_profiles import PROFILES
from .oauth_attempt import SigninAttempt

_LOCK = threading.Lock()
_ATTEMPTS: dict = {}
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
    # Read job state first: completion during credential presence reads must
    # retain the old pending state so the client polls once more.
    with _LOCK:
        jobs = {provider: dict(job) for provider, job in _JOBS.items()}
    rows = []
    for row in oauth_signin.status():
        job = jobs.get(row["provider"], {})
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


def begin(provider: str, callback_base: Optional[str] = None) -> dict:
    """Start a sign-in. A browser flow runs in the background and the caller
    polls; a guided flow returns steps for the surface to render; a
    registered provider refuses until its operator-owned registration is configured.

    callback_base is set only by a remote client (a paired phone): it is the
    engine address that client reached, and the browser flow returns the
    authorize URL for the phone to open, with a callback bound to that address
    instead of loopback. Omitted, the flow is unchanged: the browser opens on
    the engine and the callback stays on loopback."""
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
    registered = profile.kind == "registered"
    if registered:
        profile = oauth_signin._registered_profile(profile)
        if isinstance(profile, dict):
            return {**profile, "mode": "registered"}
    with _LOCK:
        if _JOBS.get(provider, {}).get("state") == "running":
            return {"ok": True, "provider": provider, "mode": "browser",
                    "note": "a sign-in is already running; finish it in the browser"}
        attempt = SigninAttempt()
        _ATTEMPTS[provider] = attempt
        _JOBS[provider] = {"state": "running"}
    server = None
    try:
        if callback_base:
            host = urllib.parse.urlparse(callback_base).hostname
            if not host:
                raise ValueError("invalid engine address")
            server, callback, verifier, url = oauth_signin._pkce_begin(
                profile, advertise_host=host)
            def action():
                return oauth_signin._pkce_finish(profile, server, callback, verifier, attempt=attempt)
        elif registered:
            def action():
                return oauth_signin._login_pkce(profile, attempt=attempt)
        else:
            def action():
                return oauth_signin.login(provider, attempt=attempt)
        thread = threading.Thread(target=_run, args=(provider, attempt, action, server),
                                  daemon=True, name=f"signin-{provider}")
        thread.start()
    except Exception:
        if server is not None:
            server.server_close()
        result = {"ok": False, "provider": provider,
                  "error": "could not start sign-in; check the engine address and try again"}
        _complete(provider, attempt, result)
        return result
    return {"ok": True, "provider": provider, "mode": "browser",
            **({"authorize_url": url} if callback_base else {}),
            "note": "open the sign-in page and approve it; completion appears here"}


def _run(provider, attempt, action, server=None):
    try:
        result = ({"ok": False, "error": "sign-in cancelled locally"}
                  if attempt.cancelled.is_set() else action())
    except Exception as exc:
        result = {"ok": False, "error": f"sign-in failed ({type(exc).__name__})"}
    if server is not None:
        try:
            server.server_close()
        except Exception:
            result = {"ok": False, "error": "could not close the sign-in listener"}
    _complete(provider, attempt, result)


def _complete(provider, attempt, result):
    attempt.finish()
    with _LOCK:
        if _ATTEMPTS.get(provider) is not attempt or attempt.cancelled.is_set():
            return
        record = {"state": "done" if result.get("ok") else "failed"}
        if result.get("error"):
            record["error"] = result["error"]
        _JOBS[provider] = record


def cancel(provider: str) -> dict:
    """Cancel local completion; an already committed store is not reversed."""
    with _LOCK:
        attempt = _ATTEMPTS.get(provider)
        if attempt is None or not attempt.cancel():
            return {"ok": False, "provider": provider, "state": "already_completed",
                    "error": "no active sign-in to cancel; refresh its final status"}
        _JOBS[provider] = {"state": "cancelled"}
        return {"ok": True, "provider": provider, "state": "cancelled"}



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
    # Claim/cancel/delete share one boundary: replacement begin cannot race
    # deletion, and a stale worker can neither store nor publish afterwards.
    with _LOCK:
        attempt = _ATTEMPTS.get(provider)
        if attempt is not None:
            attempt.cancel()
        result = oauth_signin.logout(provider)
        _ATTEMPTS.pop(provider, None)
        _JOBS.pop(provider, None)
    return result
