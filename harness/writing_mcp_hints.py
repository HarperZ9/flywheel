"""Title and hints for each Writing Workspace MCP tool.

Kept apart from `writing_operations`, which holds what each operation is, so
that module stays one table of operations and this one is the one place that
says what each tool does to the person's machine.

Every tool, status and doctor included, builds the writing service, which
creates the owner ref and state folders under the home on its first call, so
none can honestly claim readOnlyHint. Prepare tools write a proposal and change
no manuscript. Only a commit changes one, rollbacks included, so it alone is
destructive. No tool leaves the machine.
"""
from __future__ import annotations

from .mcp_annotations import annotated

# name: (title, destructive, idempotent). readOnlyHint is false for all.
HINTS: dict[str, tuple[str, bool, bool]] = {
    "writing.status": ("List writing projects", False, True),
    "writing.doctor": ("Check writing workspace readiness", False, True),
    "writing.project_init": ("Prepare a project proposal", False, False),
    "writing.section_record": ("Prepare a section proposal", False, False),
    "writing.revision_record": ("Prepare a revision proposal", False, False),
    "writing.diagnose": ("Prepare a reader-flow diagnostic", False, False),
    "writing.card_record": ("Prepare an author card proposal", False, False),
    "writing.candidate_record": ("Prepare a candidate proposal", False, False),
    "writing.decision_record": ("Prepare a decision proposal", False, False),
    "writing.review_prepare": ("Prepare a review proposal", False, False),
    "writing.export_prepare": ("Prepare an export proposal", False, False),
    "writing.proposal_get": ("Read a proposal preview", False, True),
    "writing.proposal_approve": ("Approve a proposal (CLI only)", False, True),
    "writing.proposal_commit": ("Commit an approved proposal", True, False),
}


def hinted(tool: dict) -> dict:
    title, destructive, idempotent = HINTS[tool["name"]]
    return annotated(tool, title, read_only=False, destructive=destructive,
                     idempotent=idempotent, open_world=False)
