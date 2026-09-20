"""Studio body acceptance checks for the frozen Flywheel gateway."""
from __future__ import annotations
import json
import urllib.error
import urllib.request
from scripts.frozen_gateway_studio_contract import (
    ENGINE_ACTION_KIND,
    ENGINE_TARGET,
    STATUS_ROUTE,
    STEP_ROUTE,
    STEP_SCHEMA,
    SUMMARY_SCHEMA,
    UNVERIFIED,
    StudioSmokeFixture,
    engine_render_body,
    off_target_engine_render_body,
    prepare_studio_smoke_fixture,
    require,
    status_summary,
    ungranted_sound_body,
    validate_authority,
    validate_engine_receipt,
    validate_fixture,
    validate_status,
    validate_studio_smoke_summary,
)
def request_json(base: str, path: str, token: str | None, *,
                 body: dict | None = None,
                 secret_values: tuple[str, ...] = ()) -> tuple[int, dict]:
    headers = {"Authorization": "Bearer " + token} if token else {}
    data, method = None, "GET"
    if body is not None:
        data = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        headers["Content-Type"], method = "application/json", "POST"
    request = urllib.request.Request(base + path, data=data, headers=headers,
                                     method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(request, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read(2_000_001)
    require(len(raw) <= 2_000_000, "OVERSIZED_RESPONSE")
    try:
        text = raw.decode("utf-8")
        value = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("JSON_RESPONSE_SHAPE") from exc
    for secret in (*secret_values, token):
        require(not secret or secret not in text, "CREDENTIAL_ECHO")
    require(type(value) is dict, "JSON_RESPONSE_SHAPE")
    return response.code, value
def run_studio_acceptance_smoke(
        base: str, token: str, fixture: StudioSmokeFixture, *,
        request=request_json) -> dict:
    validate_fixture(fixture)
    routes: list[str] = []
    secrets = (token,)
    unauth_status, auth = _call(request, base, None, STATUS_ROUTE, routes, secrets)
    require(unauth_status == 401
            and auth.get("error", {}).get("code") == "AUTH_REQUIRED",
            "STUDIO_AUTH_REQUIRED")
    code, status = _call(request, base, token, STATUS_ROUTE, routes, secrets)
    require(code == 200, "HTTP_FAILURE:" + STATUS_ROUTE)
    validate_status(status)
    denied_code, denied = _post(
        request, base, token, STEP_ROUTE, routes, ungranted_sound_body(), secrets)
    _require_refusal(denied_code, denied, "STUDIO_UNGRANTED_ACTION_REFUSAL")
    off_target_code, off_target = _post(
        request, base, token, STEP_ROUTE, routes,
        off_target_engine_render_body(), secrets)
    exact_scope_checked = _require_refusal(
        off_target_code, off_target, "STUDIO_OFF_TARGET_ACTION_REFUSAL")
    accepted = _post_ok(
        request, base, token, STEP_ROUTE, routes, engine_render_body(1), secrets)
    require(accepted.get("schema") == STEP_SCHEMA, "STUDIO_STEP_SCHEMA")
    require(accepted.get("accepted") is True and accepted.get("status") == "accepted",
            "STUDIO_RENDER_NOT_ACCEPTED")
    require(accepted.get("action_kind") == ENGINE_ACTION_KIND, "STUDIO_ACTION_KIND")
    require(accepted.get("target") == ENGINE_TARGET, "STUDIO_TARGET")
    receipt = accepted.get("receipt")
    first_frame_sha, frame_count = validate_engine_receipt(receipt)
    exhausted_code, exhausted = _post(
        request, base, token, STEP_ROUTE, routes, engine_render_body(2), secrets)
    _require_refusal(exhausted_code, exhausted, "STUDIO_ONE_USE_EXHAUSTION")
    summary = {
        "schema": SUMMARY_SCHEMA,
        "unauthenticated_status": unauth_status,
        "status": status_summary(status),
        "ungranted_action_status": denied_code,
        "off_target_action_status": off_target_code,
        "exhausted_action_status": exhausted_code,
        "accepted": True,
        "action_kind": ENGINE_ACTION_KIND,
        "target": ENGINE_TARGET,
        "world_id": receipt.get("world_id"),
        "frame_count": frame_count,
        "first_frame_sha256": first_frame_sha,
        "authority": validate_authority(accepted.get("authority_receipt")),
        "exact_scope_checked": exact_scope_checked,
        "routes": routes,
        "unverified": list(UNVERIFIED),
    }
    validate_studio_smoke_summary(summary)
    return summary
def _require_refusal(code: int, value: dict, failure: str) -> bool:
    require(code == 403 and value.get("accepted") is False
            and value.get("receipt") is None, failure)
    authority = value.get("authority_receipt")
    require(isinstance(authority, dict)
            and authority.get("decision") != "allow"
            and authority.get("acted") is False, failure)
    return True
def _call(request, base, token, path, routes, secrets):
    routes.append(path.split("?", 1)[0])
    return request(base, path, token, secret_values=secrets)
def _post(request, base, token, path, routes, body, secrets):
    routes.append(path)
    return request(base, path, token, body=body, secret_values=secrets)
def _post_ok(request, base, token, path, routes, body, secrets):
    code, value = _post(request, base, token, path, routes, body, secrets)
    require(code == 200, "HTTP_FAILURE:" + path)
    return value
