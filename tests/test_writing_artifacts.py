import os
import subprocess

import pytest

from harness.writing_artifacts import WritingArtifactError, WritingArtifactStore
from harness.writing_types import sha256_bytes


OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_artifact_refs_are_private_opaque_and_owner_scoped(tmp_path):
    store = WritingArtifactStore(tmp_path / "state")
    value = {
        "schema": "flywheel.writing-project-brief/v1",
        "project_ref": PROJECT,
        "mode": "nonfiction",
        "form": "essay",
        "working_title": "Release evidence",
        "audience": "operators",
        "reader_job": "decide whether to ship",
        "author_intent": "tighten decision support",
        "voice_contract": {"style_ref": "voice_rules"},
        "source_packet_ref": "packet_main",
        "writing_profile": "nonfiction",
        "does_not_prove": ["source truth"],
    }

    record = store.write_json(OWNER, PROJECT, "brief", "brief", value)
    loaded = store.read_json(record["artifact_ref"], record["artifact_sha256"])

    assert loaded == value
    assert record["artifact_ref"].startswith(
        f"writing/v1/owners/{OWNER}/projects/{PROJECT}/brief/"
    )
    assert str(tmp_path) not in record["artifact_ref"]
    assert record["artifact_sha256"] == sha256_bytes(record["artifact_bytes"])


def test_artifact_reader_rejects_escape_symlink_and_over_cap_reads(tmp_path):
    store = WritingArtifactStore(tmp_path / "state")
    with pytest.raises(WritingArtifactError, match="ARTIFACT_REF_INVALID"):
        store.read_text("../../outside.txt")

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = store.root / "writing" / "v1" / "owners" / OWNER / "projects" / PROJECT
    link.mkdir(parents=True)
    try:
        os.symlink(outside, link / "escaped.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")

    with pytest.raises(WritingArtifactError, match="ARTIFACT_AUTHORITY"):
        store.read_text(
            f"writing/v1/owners/{OWNER}/projects/{PROJECT}/escaped.txt"
        )

    big = store.root / "writing" / "v1" / "owners" / OWNER / "projects" / PROJECT / "body"
    big.mkdir(parents=True, exist_ok=True)
    (big / "huge.txt").write_bytes(b"x" * 33)
    with pytest.raises(WritingArtifactError, match="ARTIFACT_TOO_LARGE"):
        store.read_text(
            f"writing/v1/owners/{OWNER}/projects/{PROJECT}/body/huge.txt",
            max_bytes=32,
        )


def test_artifacts_are_immutable_by_digest(tmp_path):
    store = WritingArtifactStore(tmp_path / "state")
    first = store.write_text(OWNER, PROJECT, "body", "draft", "one\r\ntwo")
    same = store.write_text(OWNER, PROJECT, "body", "draft", "one\ntwo")

    assert same["artifact_ref"] == first["artifact_ref"]
    assert store.read_text(first["artifact_ref"]) == "one\ntwo"
    with pytest.raises(WritingArtifactError, match="ARTIFACT_EXISTS"):
        store.write_text(OWNER, PROJECT, "body", "draft", "changed")


def test_author_json_rejects_unknown_fields(tmp_path):
    store = WritingArtifactStore(tmp_path / "state")
    value = {
        "schema": "flywheel.writing-section/v1",
        "project_ref": PROJECT,
        "section_ref": "sec_intro",
        "heading": "Intro",
        "purpose": "open the piece",
        "reader_entry_state": "needs context",
        "promises": ["sets up the decision"],
        "order_index": 1,
        "quality_claim": "great",
    }
    with pytest.raises(Exception, match="ARTIFACT_FIELDS_INVALID"):
        store.write_json(OWNER, PROJECT, "section", "sec_intro", value)


def test_artifact_root_rejects_junction_or_symlink_authority(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    root = state / "artifacts"
    if os.name == "nt":
        created = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"New-Item -ItemType Junction -Path '{root}' -Target '{outside}' | Out-Null"],
            capture_output=True, text=True, timeout=20)
        if created.returncode:
            pytest.skip("junction creation unavailable")
    else:
        os.symlink(outside, root)
    with pytest.raises(WritingArtifactError, match="ARTIFACT_AUTHORITY"):
        WritingArtifactStore(state)
