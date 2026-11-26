"""Deterministic full-signal parsing and media deconstruction pipeline for Gather."""
from __future__ import annotations

from gather.deconstruct.audio_deconstruct import AUDIO_SCHEMA, deconstruct_audio
from gather.deconstruct.cmd import add_deconstruct_parser
from gather.deconstruct.paper_deconstruct import PAPER_SCHEMA, deconstruct_paper
from gather.deconstruct.video_media_deconstruct import (
    MEDIA_SCHEMA,
    deconstruct_artifact,
)
from gather.deconstruct.workflows import (
    civic_provenance_workflow,
    media_to_distill_workflow,
    research_to_verify_workflow,
)

__all__ = [
    "AUDIO_SCHEMA",
    "MEDIA_SCHEMA",
    "PAPER_SCHEMA",
    "add_deconstruct_parser",
    "civic_provenance_workflow",
    "deconstruct_artifact",
    "deconstruct_audio",
    "deconstruct_paper",
    "media_to_distill_workflow",
    "research_to_verify_workflow",
]
