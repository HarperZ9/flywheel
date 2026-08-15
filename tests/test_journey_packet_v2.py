import hashlib
import json
import shutil

import harness.journey_packet_v2 as packet_module

import pytest

from harness.evidence_json import canonical_bytes, canonical_sha256
from harness.evidence_packet_validation import verify_journey_packet
from harness.journey_packet_v2 import (
    PACKET_PROFILE, pack_journey_custody_packet,
    verify_journey_custody_packet,
)
from harness.journey_projection import reduce_events
from harness.journey_types import build_event

OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
NOW = "2026-08-14T12:00:00Z"


def _events():
    events, head = [], None
    for sequence, event_type, payload in (
            (0, "intake", {"legacy_label": None, "goal": "Accept custody", "intake": {}}),
            (1, "decomposed", {}),
            (2, "preflight", {}),
            (3, "running", {}),
            (4, "concluded", {"conclusion": {"summary": "bounded"}}),
    ):
        event = build_event(
            journey_ref=JOURNEY, sequence=sequence, event_type=event_type,
            occurred_at=NOW, actor_id=OWNER,
            request_sha256=canonical_sha256({"sequence": sequence}),
            payload=payload, prior_event_sha256=head,
        )
        events.append(event); head = event["event_sha256"]
    return events


def _packet(tmp_path):
    events = _events()
    projection = reduce_events(events)
    result = pack_journey_custody_packet(
        tmp_path / "packet", events=events, projection=projection)
    return tmp_path / "packet", events, projection, result


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _store(path, value):
    path.write_text(json.dumps(value, indent=1, sort_keys=True), encoding="utf-8")


def _seal(packet, rel):
    manifest = _load(packet / "manifest.json")
    raw = (packet / rel).read_bytes()
    for item in manifest["files"]:
        if item["path"] == rel:
            item["sha256"] = hashlib.sha256(raw).hexdigest()
            item["bytes"] = len(raw)
    _store(packet / "manifest.json", manifest)


def test_custody_packet_rechecks_clean_copy_without_oracle_or_host_paths(tmp_path):
    """A clean copied packet must recheck v2 custody without store or oracle access."""
    packet, events, projection, result = _packet(tmp_path)
    clean = tmp_path / "clean" / "packet"; clean.parent.mkdir()
    shutil.copytree(packet, clean)
    anchor = "sha256:" + hashlib.sha256((clean / "manifest.json").read_bytes()).hexdigest()
    unanchored = verify_journey_custody_packet(clean)
    anchored = verify_journey_custody_packet(clean, expected_manifest_sha256=anchor)
    criterion = _load(clean / "criterion.json")
    carried = b"".join(path.read_bytes() for path in clean.rglob("*") if path.is_file())
    assert result["profile"] == criterion["profile"] == PACKET_PROFILE
    assert criterion["source_event_head_sha256"] == events[-1]["event_sha256"]
    assert criterion["source_projection_sha256"] == canonical_sha256(projection)
    assert unanchored["structural_verdict"] == "MATCH"
    assert unanchored["verdict"] == "UNVERIFIABLE"
    assert anchored["verdict"] == "MATCH"
    drifted = verify_journey_custody_packet(
        clean, expected_manifest_sha256="sha256:" + "0" * 64)
    assert drifted["verdict"] == drifted["rehash_resistance_verdict"] == "DRIFT"
    assert str(tmp_path).encode() not in carried
    assert b"Zain" not in carried and b"credential" not in carried


@pytest.mark.parametrize("rel,mutate", [
    ("events.json", lambda value: [dict(value[0], actor_id="owner_bad"), *value[1:]]),
    ("projection.json", lambda value: {**value, "stage": "exported"}),
    ("tree_head.json", lambda value: {**value, "size": 999}),
    ("custody_receipt.json", lambda value: {**value, "structural_verdict": "FAIL"}),
    ("criterion.json", lambda value: {**value, "profile": "flywheel.evidence-journey-custody/v3"}),
])
def test_rehashed_tamper_of_each_custody_fact_fails_closed(tmp_path, rel, mutate):
    """Rehashing after semantic tamper must not make custody MATCH."""
    packet, _, _, _ = _packet(tmp_path)
    changed = mutate(_load(packet / rel))
    if rel == "criterion.json":
        changed.pop("criterion_sha256", None)
        changed["criterion_sha256"] = canonical_sha256(changed)
    if rel == "custody_receipt.json":
        changed.pop("receipt_sha256", None)
        changed["receipt_sha256"] = canonical_sha256(changed)
    _store(packet / rel, changed); _seal(packet, rel)
    assert verify_journey_custody_packet(packet)["verdict"] == "DRIFT"


@pytest.mark.parametrize("case", (
    "extra", "missing", "traversal", "drive", "file_uri", "duplicate",
    "oversized", "deep", "inventory",
))
def test_packet_preflight_rejects_hostile_layouts_before_semantics(tmp_path, case):
    """Manifest drift, traversal, duplicate JSON keys, and size abuse fail closed."""
    packet, _, _, _ = _packet(tmp_path)
    if case == "extra":
        (packet / "extra.json").write_text("{}", encoding="utf-8")
    elif case == "missing":
        (packet / "tree_head.json").unlink()
    elif case in {"traversal", "drive", "file_uri"}:
        manifest = _load(packet / "manifest.json")
        unsafe = {"traversal": "../outside.json", "drive": "C:/outside.json",
                  "file_uri": "file:///outside.json"}[case]
        manifest["files"][0]["path"] = unsafe
        _store(packet / "manifest.json", manifest)
    elif case == "duplicate":
        (packet / "criterion.json").write_bytes(b'{"schema":"x","schema":"y"}')
        _seal(packet, "criterion.json")
    elif case == "oversized":
        (packet / "events.json").write_bytes(b"x" * 1_048_577)
        _seal(packet, "events.json")
    elif case == "deep":
        value = _load(packet / "projection.json")
        value["conclusion"] = {"nested": {"nested": {"nested": {"nested": {
            "nested": {"nested": {"nested": {"nested": "too deep"}}}}}}}}
        _store(packet / "projection.json", value); _seal(packet, "projection.json")
    else:
        manifest = _load(packet / "manifest.json")
        manifest["files"] = list(reversed(manifest["files"]))
        _store(packet / "manifest.json", manifest)
    assert verify_journey_custody_packet(packet)["verdict"] == "UNVERIFIABLE"


def test_packet_preflight_rejects_link_before_file_read(tmp_path, monkeypatch):
    """A link or reparse entry must be rejected before its bytes are trusted."""
    packet, _, _, _ = _packet(tmp_path)
    original = packet_module._reparse
    monkeypatch.setattr(packet_module, "_reparse", lambda path:
                        path.name == "events.json" or original(path))
    assert verify_journey_custody_packet(packet)["verdict"] == "UNVERIFIABLE"


def test_legacy_v1_packet_verifier_rejects_v2_profile(tmp_path):
    """A legacy-only verifier must not silently accept the Journey-v2 packet arm."""
    packet, _, _, _ = _packet(tmp_path)
    assert verify_journey_packet(packet)["verdict"] != "MATCH"
