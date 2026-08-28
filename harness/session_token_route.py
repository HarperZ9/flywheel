"""HTTP transport for session token operations."""
from __future__ import annotations

from .session_token import SessionTokenError, SessionTokenStore

MAX_TTL = 3600


def session_token_post(
    action: str,
    raw: dict,
    *,
    owner_ref: str,
    token_store: SessionTokenStore,
) -> tuple[dict, int]:
    if action == "mint":
        refs = raw.get("credential_refs")
        slots = raw.get("required_slots")
        session = raw.get("session_ref")
        ttl = raw.get("ttl_seconds", 900)
        if (not isinstance(refs, list) or not isinstance(slots, list)
                or not isinstance(session, str) or not session
                or not isinstance(ttl, int) or ttl < 0):
            return {"ok": False, "error": "INVALID_REQUEST"}, 400
        ttl = min(ttl, MAX_TTL)
        try:
            token = token_store.mint(owner_ref, session, refs, slots, ttl)
        except (SessionTokenError, Exception) as e:
            code = e.code if isinstance(e, SessionTokenError) else "STORE_ERROR"
            return {"ok": False, "error": code}, 400
        return {"ok": True, "token_ref": token.token_ref,
                "session_ref": token.session_ref,
                "expires_at": token.expires_at}, 200

    if action == "revoke":
        ref = raw.get("token_ref", "")
        if not isinstance(ref, str) or not ref:
            return {"ok": False, "error": "INVALID_REQUEST"}, 400
        ok = token_store.revoke(ref, owner_ref)
        return {"ok": ok}, 200 if ok else 404

    return {"ok": False, "error": "UNKNOWN_ACTION"}, 404


def session_token_get(
    *, owner_ref: str, token_store: SessionTokenStore,
) -> tuple[dict, int]:
    tokens = token_store.list_active(owner_ref)
    return {"ok": True, "tokens": [
        {"token_ref": t.token_ref, "session_ref": t.session_ref,
         "slots": len(t.required_slots), "expires_at": t.expires_at}
        for t in tokens
    ]}, 200
