"""Native route acceptance checks for the frozen Flywheel gateway.

The checker process owns the loopback Bulletin stand-in and synthetic fixture
state. The executable under test owns the gateway routes, grant validation,
credential resolution, signing, upload, and readback decisions.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
from urllib.parse import quote
import urllib.error
import urllib.request
import zlib

from .frozen_gateway_media_board import LoopbackMediaBoard
from .frozen_gateway_native_payloads import WRITING_BODY, brief, media_post, section, source_packet
BULLETIN_KEY_SLOT = "BULLETIN_AGENT_JWK"
MEDIA_JOURNEY = "jrn_" + "f" * 32
def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))


_scanlines = b"".join((
    b"\x00\x80\x20\xa0\xff\xc0\x20\xa0\xff",
    b"\x00\x80\x60\xa0\xff\xc0\x60\xa0\xff"))
_PNG = (b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(_scanlines))
        + _png_chunk(b"IEND", b""))


@dataclass
class NativeSmokeFixture:
    key_json: str
    public_jwk: dict[str, str]
    board: LoopbackMediaBoard
    media_journey_ref: str
    media_event_head: str
    credential_ref: str
    run_id: str
    artifact_id: str
    artifact_sha256: str
    artifact_bytes: int


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def prepare_native_smoke_fixture(home: Path, run_root: Path) -> NativeSmokeFixture:
    from harness.bulletin_identity_key import generate_identity_json, parse_identity_json
    from harness.credential_handles import CredentialHandleStore
    from harness.file_backed_store import FileBackedHarnessStore
    from harness.gateway_auth import load_or_create_owner_ref
    from harness.journey_store import JourneyStore, MutationCommand

    home = Path(home).resolve()
    run_root = Path(run_root).resolve()
    owner = load_or_create_owner_ref(home)
    key_json = generate_identity_json()
    identity = parse_identity_json(key_json)
    state_root = home / "state"
    handle = CredentialHandleStore(
        state_root, keychain_get=lambda name: key_json if name == BULLETIN_KEY_SLOT else None
    ).bind(owner, BULLETIN_KEY_SLOT)
    source = home / "frozen-native-smoke.png"
    source.write_bytes(_PNG)
    store = FileBackedHarnessStore(run_root)
    run = store.create_run(kind="creative", title="frozen native smoke")
    artifact = store.copy_artifact(source, run_id=run["run_id"], label="smoke art")
    head = JourneyStore(state_root).create(MutationCommand(
        owner, MEDIA_JOURNEY, None, "frozen-native-media-create", "intake",
        {"legacy_label": None, "goal": "publish selected artifact",
         "intake": {}, "occurred_at": "2026-09-09T12:00:00Z"})).event_head_sha256
    board = LoopbackMediaBoard(identity.public_jwk)
    return NativeSmokeFixture(
        key_json, identity.public_jwk, board, MEDIA_JOURNEY, head,
        handle.credential_ref, run["run_id"], artifact["artifact_id"],
        artifact["sha256"], len(_PNG))


def request_json(base: str, path: str, token: str, *, body: dict | None = None,
                 secret_values: tuple[str, ...] = ()) -> tuple[int, dict]:
    headers = {"Authorization": "Bearer " + token}
    data = None
    if body is not None:
        data = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers,
                                     method="POST" if body is not None else "GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(request, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read(2_000_001)
    require(len(raw) <= 2_000_000, "OVERSIZED_RESPONSE")
    text = raw.decode("utf-8")
    for secret in secret_values:
        require(not secret or secret not in text, "CREDENTIAL_ECHO")
    value = json.loads(text)
    require(type(value) is dict, "JSON_RESPONSE_SHAPE")
    return response.code, value


def run_native_acceptance_smoke(base: str, token: str,
                                fixture: NativeSmokeFixture) -> dict:
    secrets = (token, fixture.key_json)
    summary = {
        "writing": run_writing_acceptance_smoke(base, token, secrets=secrets),
        "bulletin_media": run_bulletin_media_acceptance_smoke(
            base, token, fixture, secrets=secrets),
    }
    validate_native_smoke_summary(summary)
    return summary


def run_writing_acceptance_smoke(
        base: str, token: str, *, secrets: tuple[str, ...] = (),
        request=request_json) -> dict:
    routes: list[str] = []
    project = "wpr_" + "a" * 32
    section_ref = "sec_acceptance"
    code, status = _call(request, base, token, "/api/writing/status", routes,
                         secrets=secrets)
    require(code == 200 and status.get("schema") == "flywheel.writing-status/v1",
            "WRITING_STATUS")
    init = _post(request, base, token, "/api/writing/init/prepare", routes, {
        "brief": brief(project), "source_packet": source_packet(project),
        "client_request_id": "frozen-native-writing-init"}, secrets)
    ack = _writing_commit(request, base, token, init["proposal_ref"], routes,
                          secrets)
    journey, head = ack["journey_ref"], ack["event_head_sha256"]
    section_proposal = _post(request, base, token, "/api/writing/section/prepare",
                             routes, {"journey_ref": journey,
                             "expected_event_head": head,
                             "section": section(project, section_ref),
                             "client_request_id": "frozen-native-writing-section"},
                             secrets)
    ack = _writing_commit(request, base, token, section_proposal["proposal_ref"],
                          routes, secrets)
    head = ack["event_head_sha256"]
    revision = _post(request, base, token, "/api/writing/revision/prepare",
                     routes, {"journey_ref": journey,
                     "expected_event_head": head, "project_ref": project,
                     "section_ref": section_ref, "body": WRITING_BODY,
                     "client_request_id": "frozen-native-writing-revision"},
                     secrets)
    ack = _writing_commit(request, base, token, revision["proposal_ref"], routes,
                          secrets)
    head = ack["event_head_sha256"]
    query = quote(journey, safe="")
    code, project_view = _call(
        request, base, token, f"/api/writing/project?journey_ref={query}",
        routes, secrets=secrets)
    require(code == 200 and project_view.get("journey_ref") == journey,
            "WRITING_PROJECT")
    sections = project_view.get("sections")
    require(type(sections) is list and sections and
            sections[0].get("current_body") == WRITING_BODY,
            "WRITING_STATE_DRIFT")
    return {"journey_ref": journey, "event_head_sha256": head,
            "current_body_sha256": hashlib.sha256(
                WRITING_BODY.encode()).hexdigest(), "routes": routes}


def run_bulletin_media_acceptance_smoke(
        base: str, token: str, fixture: NativeSmokeFixture, *,
        secrets: tuple[str, ...] = (), request=request_json) -> dict:
    routes: list[str] = []
    runs = _post(request, base, token,
                 "/api/gateway-grants/bulletin-media-runs", routes,
                 {"schema": "flywheel.bulletin-media-runs-request/v1",
                  "limit": 50}, secrets)
    run = next((row for row in runs.get("runs", [])
                if row.get("run_id") == fixture.run_id), None)
    require(run is not None and run.get("artifact_count") == 1, "MEDIA_RUN")
    artifacts = _post(request, base, token,
                      "/api/gateway-grants/bulletin-media-artifacts", routes,
                      {"schema": "flywheel.bulletin-media-artifacts-request/v1",
                       "run_id": fixture.run_id}, secrets)
    artifact = next((row for row in artifacts.get("artifacts", [])
                     if row.get("artifact_id") == fixture.artifact_id), None)
    require(artifact is not None and artifact.get("sha256") == fixture.artifact_sha256,
            "MEDIA_ARTIFACT")
    require(not ({"source_path", "stored_path", "relative_path"} & set(artifact)),
            "MEDIA_PRIVATE_PATH")
    selection = {
        "schema": "flywheel.outcome-bulletin-media-selection/v1",
        "journey_ref": fixture.media_journey_ref,
        "expected_event_head": fixture.media_event_head,
        "client_request_id": "frozen-native-media",
        "credential_ref": fixture.credential_ref,
        "run_id": fixture.run_id,
        "destination": {"base_url": fixture.board.url},
        "post": media_post(),
        "media": [{"artifact_id": fixture.artifact_id,
                   "alt": "Synthetic image selected from the packaged gateway smoke run."}],
    }
    prepared = _post(request, base, token,
                     "/api/gateway-grants/bulletin-media-preview", routes,
                     selection, secrets)
    proposal, operation = prepared["proposal"], prepared["operation"]
    fixture.board.preview = operation["operation"]["args"]
    review = proposal["summary"]["bulletin_media_review"]
    media = _post(request, base, token,
                  "/api/gateway-grants/bulletin-media-preview-bytes", routes,
                  {"schema": "flywheel.bulletin-media-preview-bytes-request/v1",
                   "proposal_ref": proposal["proposal_ref"],
                   "preview_ref": review["preview_media"][0]["preview_ref"],
                   "preview_sha256": review["preview_sha256"]}, secrets)
    raw = base64.b64decode(media["body_b64"])
    require(media.get("sha256") == fixture.artifact_sha256 and
            len(raw) == fixture.artifact_bytes, "MEDIA_PREVIEW_BYTES")
    approval = _post(request, base, token, "/api/gateway-grants/approve-once",
                     routes, {"proposal_ref": proposal["proposal_ref"]},
                     secrets)
    final_body = {"schema": operation["schema"],
                  "journey_ref": operation["journey_ref"],
                  "expected_event_head": operation["expected_event_head"],
                  "client_request_id": operation["client_request_id"],
                  "grant_ref": approval["grant_ref"],
                  **operation["operation"]}
    publication = _post(request, base, token,
                        "/api/lane/bulletin/board_publish_media_post", routes,
                        final_body, secrets)
    require(publication.get("status") == "posted_readback_match",
            "BULLETIN_MEDIA_RESULT")
    require(fixture.board.signed_requests == 2 and len(fixture.board.posts) == 1,
            "BULLETIN_MEDIA_SIGNED_TRANSPORT")
    return {"run_id": fixture.run_id, "artifact_id": fixture.artifact_id,
            "preview_bytes": media["bytes"],
            "preview_sha256": review["preview_sha256"],
            "result_state": publication["status"],
            "signed_uploads": fixture.board.signed_requests - len(fixture.board.posts),
            "posts": len(fixture.board.posts), "routes": routes}


def validate_native_smoke_summary(summary: dict) -> None:
    writing = summary.get("writing") if type(summary) is dict else None
    media = summary.get("bulletin_media") if type(summary) is dict else None
    require(type(writing) is dict and type(media) is dict, "NATIVE_SUMMARY")
    for path in ("/api/writing/status", "/api/writing/init/prepare",
                 "/api/writing/section/prepare", "/api/writing/revision/prepare",
                 "/api/writing/project"):
        require(path in writing.get("routes", []), "WRITING_ROUTE_MISSING")
    require(re.fullmatch(r"jrn_[0-9a-f]{32}", writing.get("journey_ref", "")) is not None,
            "WRITING_JOURNEY")
    require(re.fullmatch(r"[0-9a-f]{64}", writing.get("current_body_sha256", "")) is not None,
            "WRITING_BODY_HASH")
    for path in ("/api/gateway-grants/bulletin-media-runs",
                 "/api/gateway-grants/bulletin-media-artifacts",
                 "/api/gateway-grants/bulletin-media-preview",
                 "/api/gateway-grants/bulletin-media-preview-bytes",
                 "/api/lane/bulletin/board_publish_media_post"):
        require(path in media.get("routes", []), "BULLETIN_MEDIA_ROUTE_MISSING")
    require(re.fullmatch(r"run_\d{8}T\d{6}_[0-9a-f]{12}",
                         media.get("run_id", "")), "BULLETIN_MEDIA_RUN")
    require(re.fullmatch(r"artifact_[0-9a-f]{16}", media.get("artifact_id", "")),
            "BULLETIN_MEDIA_ARTIFACT")
    require(type(media.get("preview_bytes")) is int and media["preview_bytes"] > 0,
            "BULLETIN_MEDIA_BYTES")
    require(re.fullmatch(r"[0-9a-f]{64}", media.get("preview_sha256", "")),
            "BULLETIN_MEDIA_HASH")
    require(media.get("result_state") == "posted_readback_match",
            "BULLETIN_MEDIA_RESULT")
    require(media.get("signed_uploads") == 1 and media.get("posts") == 1,
            "BULLETIN_MEDIA_TRANSPORT_COUNT")


def _call(request, base, token, path, routes, *, secrets):
    routes.append(path.split("?", 1)[0])
    return request(base, path, token, secret_values=secrets)


def _post(request, base, token, path, routes, body, secrets):
    code, value = request(base, path, token, body=body, secret_values=secrets)
    routes.append(path)
    require(code == 200, "HTTP_FAILURE:" + path)
    return value


def _writing_commit(request, base, token, proposal_ref, routes, secrets):
    approval = _post(request, base, token, "/api/writing/proposal/approve",
                     routes, {"proposal_ref": proposal_ref}, secrets)
    return _post(request, base, token, "/api/writing/proposal/commit", routes,
                 {"proposal_ref": proposal_ref, "grant_ref": approval["grant_ref"]},
                 secrets)
