"""hosts.py -- the text of a new instruction file canon is asked to create.

`canon switch --create` writes a file only when it does not exist yet; an
existing file is opted in by its owner adding the canon markers, never by canon.
A created file holds an empty canon region and, where the host needs one to
load the file at all, the header that makes it load.

Cursor reads `.cursor/rules/*.mdc` files and needs YAML frontmatter; with
`alwaysApply: true` it includes the rule in every request and ignores `globs`
(Cursor rules docs, read 2026-09-23). canon's rule file is created that way.
"""
from __future__ import annotations

REGION = "<!-- canon:begin scope=workspace -->\n<!-- canon:end -->\n"
CURSOR_FRONTMATTER = (
    "---\n"
    "description: Project instructions and resume brief maintained by canon\n"
    "alwaysApply: true\n"
    "---\n"
)


def new_host_text(target_name: str) -> str:
    """The initial text of a newly created instruction file for a target."""
    if target_name == "cursor":
        return CURSOR_FRONTMATTER + REGION
    return REGION


def cursor_frontmatter_problem(text: str) -> str | None:
    """None when a Cursor rule file opens with frontmatter that makes Cursor
    load it on every request and the canon region sits after it."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0] != "---":
        return "a Cursor rule needs YAML frontmatter on its first line"
    try:
        close = lines.index("---", 1)
    except ValueError:
        return "the Cursor rule's frontmatter is never closed"
    if "alwaysApply: true" not in lines[1:close]:
        return "without alwaysApply: true Cursor does not load the rule on every request"
    if any(line.startswith("<!-- canon:") for line in lines[1:close]):
        return "the canon region sits inside the Cursor frontmatter"
    return None
