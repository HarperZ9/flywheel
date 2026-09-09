from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_LOOPBACK_POW_BITS = 12
MAX_LOOPBACK_POW_ATTEMPTS = 1 << 20
WORKER_MIGRATIONS = (
    "schema/0001_init.sql",
    "schema/0002_rooms.sql",
    "schema/0003_surface.sql",
    "schema/0004_media.sql",
    "schema/0005_rotation.sql",
)


def validate_loopback_bulletin_base_url(value: str) -> str:
    """Return a normalized local Worker origin or fail closed."""
    if not isinstance(value, str):
        raise ValueError("BulletinBaseUrl must be a string")
    raw = value.strip()
    if not raw or "\\" in raw or any(ch.isspace() for ch in raw):
        raise ValueError("BulletinBaseUrl must be one loopback HTTP origin")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("BulletinBaseUrl must be one loopback HTTP origin") from exc
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        raise ValueError("BulletinBaseUrl must be loopback http")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("BulletinBaseUrl must not include userinfo")
    if port is None:
        raise ValueError("BulletinBaseUrl must include the local Worker port")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("BulletinBaseUrl must be an origin, not a path")
    return f"http://{parsed.netloc}"


def actual_worker_start_commands(
        state_dir: Path, *, bulletin_repo: str = "<bulletin-worker-repo>",
        port: int = 8787) -> list[str]:
    state = str(Path(state_dir))
    commands = [f"cd {bulletin_repo}", "cp wrangler.toml.example wrangler.toml"]
    commands.extend(
        "npx wrangler d1 execute bulletin --local "
        f"--persist-to {state} --file {migration}"
        for migration in WORKER_MIGRATIONS)
    commands.append(
        "npx wrangler dev --local "
        f"--persist-to {state} --port {port} --var BULLETIN_POW_BITS:12")
    return commands


def register_loopback_identity(
        base_url: str, raw_jwk: str, *, handle: str, timeout: int,
        http_get_json=None, signed_post_json=None) -> dict:
    from harness.bulletin_identity_contract import BulletinIdentityError
    from harness.bulletin_identity_key import normalize_handle, parse_identity_json
    from harness.bulletin_identity_network import agent_status, solve_proof_of_work
    from harness.bulletin_signed_transport import (
        _SignedClient,
        BulletinSignedTransportError,
    )

    base = validate_loopback_bulletin_base_url(base_url)
    identity = parse_identity_json(raw_jwk)
    normalized = normalize_handle(handle)
    known = agent_status(
        base, identity.thumbprint, http_get_json=http_get_json, timeout=timeout)
    if known.get("registered"):
        return {
            "requested": True,
            "action": "already_registered",
            "registered": True,
            "handle": known.get("handle", normalized),
            "tier": known.get("tier", ""),
        }
    challenge = _loopback_challenge(base, http_get_json, timeout=timeout)
    if challenge["bits"] > MAX_LOOPBACK_POW_BITS:
        raise BulletinIdentityError("POW_BITS_UNSUPPORTED")
    solution = solve_proof_of_work(
        challenge["challenge"], identity.thumbprint, challenge["bits"],
        max_attempts=MAX_LOOPBACK_POW_ATTEMPTS)
    payload = {
        "public_jwk": identity.public_jwk,
        "handle": normalized,
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
        "handle": agent.get("handle") if isinstance(agent.get("handle"), str) else normalized,
        "tier": agent.get("tier") if isinstance(agent.get("tier"), str) else "",
    }


def _loopback_challenge(base: str, http_get_json, *, timeout: int) -> dict[str, object]:
    from harness.bulletin_identity_contract import BulletinIdentityError

    getter = http_get_json or _http_get_json
    try:
        value = getter(f"{base}/v1/challenge", timeout=timeout)
    except TypeError:
        value = getter(f"{base}/v1/challenge")
    challenge = value.get("challenge") if isinstance(value, dict) else None
    bits = value.get("bits") if isinstance(value, dict) else None
    if not isinstance(challenge, str) or not challenge or type(bits) is not int or bits < 0:
        raise BulletinIdentityError("CHALLENGE_UNAVAILABLE")
    return {"challenge": challenge, "bits": bits}


def _http_get_json(url: str, *, timeout: int) -> dict:
    from harness.bulletin_identity_network import _http_get_json as get_json

    return get_json(url, timeout=timeout)


def public_registration(registration: dict) -> dict:
    return {
        "requested": registration.get("requested") is True,
        "action": str(registration.get("action", "")),
        "registered": registration.get("registered") is True,
        "handle": str(registration.get("handle", "")),
        "tier": str(registration.get("tier", "")),
        "pow_max_bits": MAX_LOOPBACK_POW_BITS,
        "pow_max_attempts": MAX_LOOPBACK_POW_ATTEMPTS,
    }
