"""Static payloads for the frozen gateway native smoke."""
from __future__ import annotations

WRITING_BODY = "Packaged Writing revision.\n"


def brief(project: str) -> dict:
    return {"schema": "flywheel.writing-project-brief/v2", "project_ref": project,
            "mode": "nonfiction", "form": "essay", "working_title": "Release evidence",
            "audience": "operators", "reader_job": "decide whether evidence is sufficient",
            "author_intent": "make a bounded release recommendation",
            "voice_contract": {"style_ref": "voice_rules"},
            "source_packet_ref": "packet_main", "writing_profile": "nonfiction",
            "scope": ["the brief states the project's audience, intent and voice contract"]}


def source_packet(project: str) -> dict:
    return {"schema": "flywheel.writing-source-packet/v2", "project_ref": project,
            "source_packet_ref": "packet_main", "sources": [{
                "source_id": "src_receipt", "title": "Receipt",
                "origin": "local", "allowed_use": "cite"}],
            "scope": ["the packet lists the sources and the use each one allows"]}


def section(project: str, section_ref: str) -> dict:
    return {"schema": "flywheel.writing-section/v1", "project_ref": project,
            "section_ref": section_ref, "heading": "Recommendation",
            "purpose": "state the release decision",
            "reader_entry_state": "needs a decision",
            "promises": ["states the decision"], "order_index": 1}


def media_post() -> dict:
    return {"room": "findings", "title": "Frozen gateway smoke media",
            "description": "Synthetic artifact selected from the packaged gateway smoke run.",
            "source_attribution": "Synthetic local smoke fixture.",
            "limits": ["smoke success covers the packaged gateway's media post path with a synthetic artifact; license, authorship, malware, hidden-data, UI, installer and clean-machine checks are separate steps"],
            "links": []}
