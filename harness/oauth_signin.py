"""oauth_signin.py -- the stepwise sign-in seam for subscription accounts.

subscription_auth.py stays read-only by covenant: it consumes a token an
authorized login already produced. THIS module is the login. It is explicit,
operator-initiated, and writes exactly one thing: the resulting token into
the OS credential store, under the same name the read-only adapters already
consume. No resolver rewiring; sign in, and the router sees it.

Provider honesty is typed, not implied. Each profile carries its sanction:

  - `pkce`        the provider documents a third-party PKCE flow with no app
                  registration (OpenRouter). Works out of the box.
  - `guided-cli`  the provider's own official tool mints the token (Anthropic:
                  `claude setup-token`); this module walks the user through it
                  and stores the paste. It never impersonates another app's
                  OAuth client, and it claims no provider sanction: what the
                  resulting token may be used for is governed by that
                  provider's terms, which the operator is accountable to.
  - `registered`  the provider runs a partner program; the flow lights up once
                  the operator registers the app and configures a client id.
                  Until then the honest answer is "requires registration",
                  never a borrowed client id.

Redaction discipline matches subscription_auth: a token value exists in
memory and in the credential store, and appears nowhere else. Failures are
returned as error dicts, never raised as tracebacks, and never carry a
response body (which can echo a code).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Optional

from . import keychain
from .oauth_callback import CallbackServer
from .oauth_profiles import (  # noqa: F401  (re-exported: the module API)
    PROFILES, WIRE_OAUTH2, WIRE_OPENROUTER, OAuthProfile,
)


def _pkce_pair() -> tuple[str, str]:
    """RFC 7636 S256: a high-entropy verifier and its base64url challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _fail(provider: str, error: str) -> dict:
    return {"provider": provider, "ok": False, "error": error}


def _store(profile: OAuthProfile, value: str) -> dict:
    """Persist the token, and report the credential store's own verdict. A
    write that did not happen is never reported as a success."""
    result = keychain.keychain_set(profile.keychain_name, value)
    if "error" in result:
        return _fail(profile.provider,
                     f"token obtained but NOT stored: {result['error']}. "
                     f"Export it as {profile.keychain_name} to use it.")
    return {"provider": profile.provider, "ok": True,
            "stored": profile.keychain_name, "sha256": _fingerprint(value)}


def _preflight(profile: OAuthProfile) -> Optional[dict]:
    """Refuse before minting anything we could not keep. A token created and
    then dropped is a live credential stranded at the provider."""
    if keychain.keychain_available():
        return None
    return _fail(profile.provider,
                 "no OS credential store on this platform, so a token could "
                 "not be kept. Sign in with the provider's own tool and "
                 f"export the result as {profile.keychain_name} instead.")


def _authorize_url(profile: OAuthProfile, callback: str, challenge: str,
                   state: str) -> str:
    if profile.wire == WIRE_OAUTH2:
        params = {"response_type": "code", "client_id": profile.client_id,
                  "redirect_uri": callback, "code_challenge": challenge,
                  "code_challenge_method": "S256", "state": state}
    else:
        params = {"callback_url": callback, "code_challenge": challenge,
                  "code_challenge_method": "S256"}
    joiner = "&" if "?" in profile.authorize_url else "?"
    return profile.authorize_url + joiner + urllib.parse.urlencode(params)


def _exchange_request(profile: OAuthProfile, code: str, verifier: str,
                      callback: str) -> urllib.request.Request:
    if profile.wire == WIRE_OAUTH2:
        body = urllib.parse.urlencode({
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": callback, "client_id": profile.client_id,
            "code_verifier": verifier}).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    else:
        body = json.dumps({"code": code, "code_verifier": verifier,
                           "code_challenge_method": "S256"}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
    return urllib.request.Request(profile.exchange_url, data=body,
                                  headers=headers)


def _login_pkce(profile: OAuthProfile, opener=None, timeout: float = 300,
                browser=None) -> dict:
    """Authorization-code + PKCE against a hardened loopback callback."""
    refusal = _preflight(profile)
    if refusal is not None:
        return refusal
    opener = opener or urllib.request.urlopen
    browser = browser or webbrowser.open
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    server = CallbackServer()
    callback = server.callback_url
    print(f"Opening the {profile.provider} sign-in page. Approve it there;")
    print(f"the callback returns to 127.0.0.1 on port "
          f"{server.server_address[1]}.")
    browser(_authorize_url(profile, callback, challenge, state))
    code = server.wait_for_code(timeout)   # always closes its socket
    if not code:
        detail = f" ({server.error})" if server.error else ""
        return _fail(profile.provider,
                     f"no authorization code arrived{detail}")
    try:
        with opener(_exchange_request(profile, code, verifier, callback),
                    timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _fail(profile.provider,
                     f"token exchange rejected (HTTP {exc.code})")
    except (urllib.error.URLError, OSError) as exc:
        return _fail(profile.provider,
                     f"token exchange failed ({type(exc).__name__})")
    except (ValueError, TypeError):
        return _fail(profile.provider,
                     "token exchange returned a body that was not JSON")
    key = data.get("key") or data.get("access_token") if isinstance(data, dict) else None
    if not key:
        return _fail(profile.provider,
                     "the exchange response carried no token field")
    return _store(profile, key)


def _login_guided(profile: OAuthProfile, prompt=None, **_) -> dict:
    """Walk the official tool's flow and store the pasted result. The paste
    uses getpass so the value never echoes."""
    refusal = _preflight(profile)
    if refusal is not None:
        return refusal
    if prompt is None:
        import getpass
        prompt = getpass.getpass
    print(f"Sign in to {profile.provider} via the provider's official tool:")
    for i, step in enumerate(profile.guide, 1):
        print(f"  {i}. {step}")
    value = prompt("Token (hidden): ").strip()
    if not value:
        return _fail(profile.provider, "nothing pasted; nothing stored")
    return _store(profile, value)


def _login_registered(profile: OAuthProfile, **kwargs) -> dict:
    """A partner-program flow: honest refusal until the operator registers
    the app and configures the endpoints; standard OAuth2 + PKCE after."""
    client_id = os.environ.get(profile.client_id_env, "")
    if not client_id:
        return _fail(profile.provider, profile.sanction)
    prefix = profile.client_id_env.rsplit("_CLIENT_ID", 1)[0]
    authorize = os.environ.get(f"{prefix}_AUTHORIZE_URL", "")
    exchange = os.environ.get(f"{prefix}_EXCHANGE_URL", "")
    if not authorize or not exchange:
        return _fail(profile.provider,
                     f"set {prefix}_AUTHORIZE_URL and {prefix}_EXCHANGE_URL "
                     "from the provider's registration")
    runtime = OAuthProfile(
        provider=profile.provider, kind="pkce",
        keychain_name=profile.keychain_name, sanction=profile.sanction,
        authorize_url=authorize, exchange_url=exchange,
        wire=WIRE_OAUTH2, client_id=client_id)
    return _login_pkce(runtime, **kwargs)


def login(provider: str, **kwargs) -> dict:
    profile = PROFILES.get(provider)
    if profile is None:
        return _fail(provider,
                     f"unknown provider; known: {', '.join(sorted(PROFILES))}")
    if profile.kind == "pkce":
        return _login_pkce(profile, **kwargs)
    if profile.kind == "guided-cli":
        return _login_guided(profile, **kwargs)
    return _login_registered(profile, **kwargs)


def logout(provider: str) -> dict:
    """Clear the stored token and report what actually happened, including a
    token the environment still holds (which this cannot clear)."""
    profile = PROFILES.get(provider)
    if profile is None:
        return _fail(provider, "unknown provider")
    result = keychain.keychain_delete(profile.keychain_name)
    still = keychain.credential_source(profile.keychain_name)
    out = {"provider": provider, "ok": "error" not in result,
           "cleared": profile.keychain_name}
    if "error" in result:
        out["error"] = result["error"]
    if still == "env":
        out["ok"] = False
        out["error"] = (f"{profile.keychain_name} is still set in the "
                        "environment; unset it there to finish signing out")
    return out


def status() -> list:
    """Presence and sanction per provider; labels only, never values."""
    rows = []
    for name in sorted(PROFILES):
        profile = PROFILES[name]
        rows.append({"provider": name, "kind": profile.kind,
                     "keychain_name": profile.keychain_name,
                     "present": bool(keychain.resolve_credential(profile.keychain_name)),
                     "source": keychain.credential_source(profile.keychain_name),
                     "sanction": profile.sanction})
    return rows


def cli(argv: list) -> int:
    """`flywheel auth login|logout <provider>` and `flywheel auth status`."""
    args = [a for a in argv if not a.startswith("-")]
    verb = args[0] if args else "status"
    if verb == "status":
        for row in status():
            mark = "signed-in" if row["present"] else "absent   "
            print(f"  {row['provider']:<12} {mark}  [{row['kind']}] "
                  f"{row['sanction']}")
        return 0
    if verb in ("login", "logout") and len(args) >= 2:
        result = login(args[1]) if verb == "login" else logout(args[1])
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    print("usage: flywheel auth [status | login <provider> | logout <provider>]")
    print(f"providers: {', '.join(sorted(PROFILES))}")
    return 2
