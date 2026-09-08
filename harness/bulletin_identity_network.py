"""Read and signed-registration calls for Bulletin identity setup."""
from __future__ import annotations

import hashlib
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote

from .bulletin_identity_contract import (
    DEFAULT_TIMEOUT,
    MAX_POW_BITS,
    BulletinIdentityError,
    BulletinIdentityHttpError,
)
from .bulletin_identity_key import BulletinIdentity
from .bulletin_signed_transport import (
    _NO_REDIRECT,
    _SignedClient,
    BulletinSignedTransportError,
    bulletin_request,
)
from .evidence_json import strict_load_json


def agent_status(
        base: str, thumbprint: str, *, http_get_json: Callable[..., dict] | None,
        timeout: int) -> dict:
    url = f"{base}/v1/agents/{quote(thumbprint, safe='')}"
    try:
        value = _call_get_json(http_get_json, url, timeout=timeout)
    except BulletinIdentityHttpError as exc:
        if exc.status == 404:
            return {"registered": False}
        raise BulletinIdentityError("BOARD_STATUS_UNAVAILABLE") from None
    if not isinstance(value, dict) or value.get("ok") is not True:
        return {"registered": False}
    agent = value.get("agent") if isinstance(value.get("agent"), dict) else {}
    out = {"registered": True}
    if isinstance(agent.get("handle"), str):
        out["handle"] = agent["handle"]
    if isinstance(agent.get("tier"), str):
        out["tier"] = agent["tier"]
    return out


def register_or_reuse(
        identity: BulletinIdentity, base: str, handle: str, *, known_status: dict,
        http_get_json: Callable[..., dict] | None,
        signed_post_json: Callable[[str, dict], dict] | None,
        timeout: int, max_pow_bits: int = MAX_POW_BITS) -> dict:
    if known_status.get("registered"):
        return {
            "requested": True,
            "action": "already_registered",
            "registered": True,
            "handle": known_status.get("handle", handle),
            "tier": known_status.get("tier", ""),
        }
    challenge = _challenge(base, http_get_json=http_get_json, timeout=timeout)
    bits = challenge["bits"]
    if bits > max_pow_bits:
        raise BulletinIdentityError("POW_BITS_UNSUPPORTED")
    solution = solve_proof_of_work(
        challenge["challenge"], identity.thumbprint, bits,
        max_attempts=1 << max_pow_bits)
    payload = {
        "public_jwk": identity.public_jwk,
        "handle": handle,
        "challenge": challenge["challenge"],
        "solution": solution,
    }
    try:
        if signed_post_json is None:
            posted = _SignedClient(
                base, identity.signer(), timeout=timeout, now=None,
                nonce_bytes=None).post_json("/v1/agents", payload)
        else:
            posted = signed_post_json("/v1/agents", payload)
    except BulletinSignedTransportError:
        raise BulletinIdentityError("REGISTRATION_UNAVAILABLE") from None
    if not isinstance(posted, dict) or posted.get("ok") is not True:
        raise BulletinIdentityError("REGISTRATION_FAILED")
    agent = posted.get("agent") if isinstance(posted.get("agent"), dict) else {}
    action = "already_registered" if posted.get("already_registered") is True else "registered"
    return {
        "requested": True,
        "action": action,
        "registered": True,
        "handle": agent.get("handle") if isinstance(agent.get("handle"), str) else handle,
        "tier": agent.get("tier") if isinstance(agent.get("tier"), str) else "",
    }


def solve_proof_of_work(
        challenge: str, thumbprint: str, required_bits: int, *,
        max_attempts: int = 1 << MAX_POW_BITS) -> str:
    if required_bits < 0:
        raise BulletinIdentityError("POW_BITS_UNSUPPORTED")
    for attempt in range(max_attempts):
        solution = _base36(attempt)
        raw = f"bulletin-pow:v1:{challenge}:{thumbprint}:{solution}".encode()
        if _leading_zero_bits(hashlib.sha256(raw).digest()) >= required_bits:
            return solution
    raise BulletinIdentityError("POW_UNSOLVED")


def _challenge(
        base: str, *, http_get_json: Callable[..., dict] | None,
        timeout: int) -> dict[str, object]:
    value = _call_get_json(http_get_json, f"{base}/v1/challenge", timeout=timeout)
    challenge = value.get("challenge") if isinstance(value, dict) else None
    bits = value.get("bits") if isinstance(value, dict) else None
    if not isinstance(challenge, str) or not challenge or type(bits) is not int or bits < 0:
        raise BulletinIdentityError("CHALLENGE_UNAVAILABLE")
    return {"challenge": challenge, "bits": bits}


def _call_get_json(
        http_get_json: Callable[..., dict] | None, url: str, *, timeout: int) -> dict:
    getter = http_get_json or _http_get_json
    try:
        value = getter(url, timeout=timeout)
    except TypeError:
        value = getter(url)
    if not isinstance(value, dict):
        raise BulletinIdentityError("BOARD_STATUS_UNAVAILABLE")
    return value


def _http_get_json(url: str, *, timeout: int = DEFAULT_TIMEOUT) -> dict:
    try:
        with _NO_REDIRECT.open(
                bulletin_request(url, method="GET"), timeout=timeout) as response:
            raw = response.read(1_048_576)
    except HTTPError as exc:
        try:
            body = strict_load_json(exc.read(1_048_576), max_bytes=1_048_576, max_depth=16)
        except Exception:
            body = {}
        raise BulletinIdentityHttpError(exc.code, body if isinstance(body, dict) else {}) from None
    except (OSError, URLError, ValueError, UnicodeError, RecursionError):
        raise BulletinIdentityError("BOARD_STATUS_UNAVAILABLE") from None
    try:
        value = strict_load_json(raw, max_bytes=1_048_576, max_depth=16)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise BulletinIdentityError("BOARD_STATUS_UNAVAILABLE") from None
    if not isinstance(value, dict):
        raise BulletinIdentityError("BOARD_STATUS_UNAVAILABLE")
    return value


def _leading_zero_bits(raw: bytes) -> int:
    total = 0
    for byte in raw:
        if byte == 0:
            total += 8
            continue
        total += 8 - byte.bit_length()
        break
    return total


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    out = ""
    while value:
        value, digit = divmod(value, 36)
        out = alphabet[digit] + out
    return out
