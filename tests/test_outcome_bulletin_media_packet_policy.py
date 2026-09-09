"""Reject invalid media policies before packet creation or credential access."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("cryptography")

from harness.credential_handles import CredentialHandleStore
from harness.evidence_json import canonical_bytes, canonical_sha256
from harness.evidence_public import TransportError
from harness.gateway_operation import AuthorizedOperation
from harness.outcome_bulletin_media import build_media_preview, publish_authorized_media_preview
from tests.bulletin_media_fixtures import OWNER, PNG, jwk_json, media_request


def _auth_for_preview(preview, credential_ref="cred_" + "a" * 32):
    operation = {"name": "bulletin", "tool": "board_publish_media_post",
                 "args": preview, "governance_tier": "T2", "timeout": 20,
                 "data_refs": preview["data_refs"],
                 "credential_refs": [credential_ref]}
    return AuthorizedOperation.for_test(
        action="lane.call", operation=operation,
        scopes=("exec", "network", "plugin", "secrets"))


def _stale_owner_packet_path(state, preview):
    return (state / "bulletin-media-previews" / OWNER
            / f"{preview['packet_ref']}.json")


def _rehash_stale_preview(preview):
    preview["review"]["media_list_sha256"] = canonical_sha256(preview["media"])
    preview["review"]["post_payload_sha256"] = canonical_sha256(preview["post"])
    preview.pop("preview_sha256", None)
    preview["preview_sha256"] = canonical_sha256(preview)
    return preview


def _rewrite_stale_packet(state, preview, mutate):
    path = _stale_owner_packet_path(state, preview)
    packet = json.loads(path.read_text(encoding="utf-8"))
    mutate(packet, preview)
    path.write_bytes(canonical_bytes(packet))
    return _rehash_stale_preview(preview)


def test_alt_limit_and_duplicate_media_ids_are_rejected_before_packet(tmp_path):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    request = media_request(root)

    too_long = {
        **request,
        "media": [{**request["media"][0], "alt": "a" * 421}],
    }
    with pytest.raises(Exception):
        build_media_preview(too_long, state_root=state)
    assert not (state / "bulletin-media-previews").exists()

    duplicate_bytes = {
        **request,
        "media": [
            {**request["media"][0],
             "artifact_id": "artifact_distinct000001"},
            {**request["media"][0],
             "artifact_id": "artifact_distinct000002",
             "label": "same bytes under another request id",
             "alt": "Same bytes under a distinct request artifact id."},
        ],
    }
    with pytest.raises(Exception):
        build_media_preview(duplicate_bytes, state_root=state)
    assert not (state / "bulletin-media-previews").exists()


@pytest.mark.parametrize("stale_kind", ["too_long_alt", "duplicate_media_id"])
def test_direct_publish_revalidates_stale_packet_policy_before_key_resolution(
        tmp_path, stale_kind):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    jwk, _ = jwk_json()
    handle = CredentialHandleStore(state, keychain_get=lambda _: jwk).bind(
        OWNER, "BULLETIN_AGENT_JWK")
    preview = build_media_preview(
        media_request(root, base_url="http://127.0.0.1:1"),
        state_root=state, owner_ref=OWNER, allow_loopback=True)

    if stale_kind == "too_long_alt":
        too_long = "a" * 421

        def mutate(packet, preview):
            packet["private_media"][0]["alt"] = too_long
            packet["public_media"][0]["alt"] = too_long
            packet["post"]["attachments"][0]["alt"] = too_long
            preview["media"][0]["alt"] = too_long
            preview["post"]["attachments"][0]["alt"] = too_long
    else:
        def mutate(packet, preview):
            duplicate = packet["private_media"][0]
            for key in ("sha256", "bytes", "expected_media_id",
                        "media_type", "kind"):
                packet["private_media"][1][key] = duplicate[key]
                packet["public_media"][1][key] = duplicate[key]
                preview["media"][1][key] = duplicate[key]
            packet["private_media"][1]["relative_path"] = duplicate[
                "relative_path"]
            preview["preview_media"][1].update({
                "bytes": duplicate["bytes"],
                "kind": duplicate["kind"],
                "media_id": duplicate["expected_media_id"],
                "media_type": duplicate["media_type"],
            })
            packet["post"]["attachments"][1]["media_id"] = duplicate[
                "expected_media_id"]
            preview["post"]["attachments"][1]["media_id"] = duplicate[
                "expected_media_id"]

    preview = _rewrite_stale_packet(state, preview, mutate)
    calls = []
    result = publish_authorized_media_preview(
        _auth_for_preview(preview, credential_ref=handle.credential_ref),
        preview, state_root=state, allow_loopback=True,
        keychain_get=lambda slot: calls.append(slot) or jwk)
    assert result["status"] == "publish_unavailable"
    assert calls == []
