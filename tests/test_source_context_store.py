import json

import pytest

from harness.evidence_json import canonical_sha256
from harness.source_context_store import SourceContextError, SourceContextStore

OWNER = "owner_" + "a" * 32
OTHER = "owner_" + "b" * 32
ROOT_ID = {"platform": "windows", "volume_serial": 1, "file_index": 2}
CORPUS_ID = {"platform": "windows", "volume_serial": 1, "file_index": 3}


def _selection(text="DECISION-FACT-ALPHA\nnaïve café", corpus_digest="c" * 64):
    base = {
        "schema": "gather.readable-context/v1",
        "corpus_digest": corpus_digest,
        "selection_count": 1,
        "max_rows": 50,
        "max_total_chars": 100_000,
        "default_limit": 100_000,
        "max_catalog_bytes": 100_000_000,
        "max_catalog_rows": 100_000,
        "max_body_bytes": 100_000_000,
        "max_read_bytes": 100_000_000,
        "total_text_chars": len(text),
        "selections": [{
            "row_ref": "row_abc", "kind": "document", "id": "alpha",
            "title": "Unsafe private title", "source": "docs",
            "ref": "C:/private/source.txt", "method": "file-read",
            "sha256": "e" * 64, "verified_sha256": "f" * 64,
            "derived_from": [], "full_text_chars": 200, "body_bytes_read": 100,
            "range": {"start": 10, "end": 10 + len(text)}, "text": text,
            "omissions": [],
        }],
        "omissions": [],
        "does_not_prove": ["truth of selected source claims"],
    }
    return dict(base, selection_digest=canonical_sha256(base),
                verified=True, verified_scope="selected_rows")


def _store(path, **kwargs):
    return SourceContextStore(path, expected_state_root_identity=ROOT_ID, **kwargs)


def test_publish_is_acyclic_idempotent_and_keeps_timestamps_outside_identity(tmp_path):
    store = _store(tmp_path, clock=lambda: "2026-09-08T12:00:00Z")

    first = store.publish_selection(
        owner_ref=OWNER, state_root_identity=ROOT_ID, root_mode="flywheel_corpus",
        profile="demo", corpus_locator="tiny", corpus_root_identity=CORPUS_ID,
        gather_payload=_selection(), selected_at="2026-09-08T12:00:00Z")
    second = store.publish_selection(
        owner_ref=OWNER, state_root_identity=ROOT_ID, root_mode="flywheel_corpus",
        profile="demo", corpus_locator="tiny", corpus_root_identity=CORPUS_ID,
        gather_payload=_selection(), selected_at="2026-09-08T12:05:00Z")

    assert first["source_context_ref"] == second["source_context_ref"]
    assert first["private_payload_sha256"] == second["private_payload_sha256"]
    assert first["source_context_ref"].startswith("data_source_context.")
    assert first["source_context_ref"].split(".", 1)[1] == first["private_payload_sha256"][:32]
    assert first["projection"]["private_payload_sha256"] == first["private_payload_sha256"]
    assert first["binding"]["private_payload_sha256"] == first["private_payload_sha256"]
    assert first["binding"]["projection_sha256"] == first["projection_sha256"]
    assert "selected_at" not in json.dumps(store.read_private_for_test(OWNER, first["source_context_ref"]))
    assert "DECISION-FACT-ALPHA" not in json.dumps(first["projection"])
    assert "C:/private" not in json.dumps(first["projection"])


def test_resolve_returns_approved_snapshot_after_live_corpus_drift_and_rejects_wrong_owner(tmp_path):
    store = _store(tmp_path, clock=lambda: "2026-09-08T12:00:00Z")
    attached = store.publish_selection(
        owner_ref=OWNER, state_root_identity=ROOT_ID, root_mode="flywheel_corpus",
        profile="demo", corpus_locator="tiny", corpus_root_identity=CORPUS_ID,
        gather_payload=_selection("DECISION-FACT-ALPHA"), selected_at="one")

    resolved = store.resolve_worker_payload(OWNER, (attached["source_context_ref"],))

    assert resolved["source_payload_sha256"]
    row = resolved["contexts"][0]["rows"][0]
    assert row["text"] == "DECISION-FACT-ALPHA"
    assert row["selected_text_utf8_bytes"] == len("DECISION-FACT-ALPHA".encode("utf-8"))
    with pytest.raises(SourceContextError) as wrong:
        store.resolve_worker_payload(OTHER, (attached["source_context_ref"],))
    assert wrong.value.code == "SOURCE_CONTEXT_PERMISSION_DENIED"


def test_selected_identity_uses_normalized_utf8_text_and_character_ranges(tmp_path):
    store = _store(tmp_path, clock=lambda: "2026-09-08T12:00:00Z")
    attached = store.publish_selection(
        owner_ref=OWNER, state_root_identity=ROOT_ID, root_mode="flywheel_corpus",
        profile="demo", corpus_locator="tiny", corpus_root_identity=CORPUS_ID,
        gather_payload=_selection("DECISION-FACT-ALPHA\nnaïve café"),
        selected_at="one")

    row = store.resolve_worker_payload(
        OWNER, (attached["source_context_ref"],))["contexts"][0]["rows"][0]

    assert row["text"] == "DECISION-FACT-ALPHA\nnaïve café"
    assert row["range"] == {"start": 10, "end": 40}
    assert row["selected_text_utf8_bytes"] == len(row["text"].encode("utf-8"))


def test_crlf_selected_text_is_rejected_instead_of_silently_renormalized(tmp_path):
    with pytest.raises(SourceContextError) as exc:
        _store(tmp_path).publish_selection(
            owner_ref=OWNER, state_root_identity=ROOT_ID,
            root_mode="flywheel_corpus", profile="demo", corpus_locator="tiny",
            corpus_root_identity=CORPUS_ID,
            gather_payload=_selection("DECISION-FACT-ALPHA\r\nnaïve café"),
            selected_at="one")
    assert exc.value.code == "SOURCE_CONTEXT_SELECTION_FAILED"
