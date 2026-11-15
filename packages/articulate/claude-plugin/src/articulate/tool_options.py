"""Edit options shared by the stdio MCP tools, defined beside their schema.

allow_change names the protected change kinds an edit may make. The accepted
changes are reported in allowed_changes, and the edit plan binds the list, so a
submit cannot widen it. explain adds a change report (`changes`) to an accepted
edit result.
"""
from .edit_options import ALLOWABLE

ALLOW_CHANGE = {
    "type": "array", "items": {"type": "string", "enum": list(ALLOWABLE)},
    "description": ("protected change kinds this edit may make; each accepted change is "
                    "reported in allowed_changes. Disclosure, added first person, HTML and "
                    "math can never be allowed.")}

EXPLAIN = {"type": "boolean", "default": False,
           "description": ("add `changes`: each changed sentence before and after, the local "
                           "findings it cleared or kept, refused paragraphs and allowed changes")}

OPTIONS = {"fix": {"allow_change": ALLOW_CHANGE, "explain": EXPLAIN},
           "polish": {"allow_change": ALLOW_CHANGE, "explain": EXPLAIN},
           "edit_plan": {"allow_change": ALLOW_CHANGE},
           "edit_submit": {"explain": EXPLAIN}}


def extend(tools):
    """Add the shared edit options to the stdio tool schemas in place."""
    for tool in tools:
        tool["inputSchema"]["properties"].update(OPTIONS.get(tool["name"], {}))


def given(name, args):
    """The shared edit options a tool call supplied, by keyword."""
    return {key: args[key] for key in OPTIONS.get(name, {}) if args.get(key) is not None}
