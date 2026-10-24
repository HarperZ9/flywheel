"""An evidence packet names its scope list per version, and both versions recheck.

A v2 packet carries `scope` in criterion.json and manifest.json. A v1 packet,
written before the scope migration, carried the older name with the older
entries; the verifier reads it with that vocabulary. A packet that mixes the
two names fails closed.
"""
from __future__ import annotations

import hashlib

from harness.evidence_packet import verify_journey_packet
from harness.evidence_packet_vocab import CURRENT, V1
from harness.scope import LEGACY_SCOPE_KEY
from tests.test_evidence_packet import _load, _packet, _save_criterion, _store


def _anchor(packet):
    return "sha256:" + hashlib.sha256((packet / "manifest.json").read_bytes()).hexdigest()


def _as_v1(packet):
    """Rewrite a fresh packet into the v1 vocabulary, as a v1 packer wrote it."""
    criterion = _load(packet / "criterion.json")
    criterion.pop("scope")
    criterion.update({"schema": V1.schema, LEGACY_SCOPE_KEY: list(V1.scope)})
    criterion["pack_manifest"]["schema"] = V1.bundle_schema
    _save_criterion(packet, criterion)
    manifest = _load(packet / "manifest.json")
    manifest.pop("scope")
    manifest.update({"schema": V1.bundle_schema, LEGACY_SCOPE_KEY: V1.manifest_scope()})
    _store(packet / "manifest.json", manifest)


def test_a_new_packet_is_v2_and_names_scope(tmp_path):
    packet = _packet(tmp_path)
    criterion, manifest = _load(packet / "criterion.json"), _load(packet / "manifest.json")
    assert criterion["schema"] == CURRENT.schema and manifest["schema"] == CURRENT.bundle_schema
    assert criterion["scope"] == list(CURRENT.scope)
    assert manifest["scope"] == CURRENT.manifest_scope()
    assert LEGACY_SCOPE_KEY not in criterion and LEGACY_SCOPE_KEY not in manifest


def test_a_v1_packet_with_the_older_name_still_rechecks(tmp_path):
    packet = _packet(tmp_path)
    _as_v1(packet)
    result = verify_journey_packet(packet, expected_manifest_sha256=_anchor(packet))
    assert (result["verdict"], result["structural_verdict"]) == ("MATCH", "MATCH")
    assert result["scope"] == list(V1.scope)


def test_a_v1_packet_carrying_the_new_name_fails_closed(tmp_path):
    packet = _packet(tmp_path)
    _as_v1(packet)
    criterion = _load(packet / "criterion.json")
    criterion["scope"] = list(CURRENT.scope)
    _save_criterion(packet, criterion)
    assert verify_journey_packet(packet)["verdict"] == "DRIFT"


def test_a_v2_manifest_carrying_the_older_name_fails_closed(tmp_path):
    packet = _packet(tmp_path)
    manifest = _load(packet / "manifest.json")
    manifest[LEGACY_SCOPE_KEY] = manifest["scope"]
    _store(packet / "manifest.json", manifest)
    assert verify_journey_packet(packet)["verdict"] == "DRIFT"
