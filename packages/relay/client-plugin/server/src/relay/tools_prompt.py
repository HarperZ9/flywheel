"""tools_prompt.py -- the system text that teaches the model the tool protocol.

Kept apart from local_tools.py so the executor module stays focused on behavior.
local_tools re-exports TOOLS_SYSTEM, so importers keep using `from .local_tools
import TOOLS_SYSTEM` unchanged.
"""
from __future__ import annotations

TOOLS_SYSTEM = (
    "You can use tools by emitting lines in this exact format (one per line):\n"
    'TOOL repo_map {"path": "."}\n'
    'TOOL read_file {"path": "<path>"}\n'
    'TOOL read_file {"path": "<path>", "hashed": true}\n'
    'TOOL list_dir {"path": "<path>"}\n'
    'TOOL edit_file {"path": "<path>", "old": "<exact text>", "new": "<replacement>"}\n'
    'TOOL edit_lines {"path": "<path>", "at": "<anchor>", "new": "<replacement>"}\n'
    'TOOL edit_plan {"ops": [{"path": "<path>", "at": "<anchor>", "new": "<text>"}, ...]}\n'
    'TOOL apply_diff {"path": "<path>", "diff": "@@ ... @@\\n context\\n-old\\n+new"}\n'
    'TOOL write_file {"path": "<path>", "content": "<text>"}\n'
    'TOOL run {"cmd": "<shell command>"}\n'
    "Prefer repo_map then read_file to locate code. To change a file, read it with "
    '"hashed": true first: every line comes back as <8hex>|<line>, and the 8-hex '
    "prefix is that line's anchor. Then edit by anchor: edit_lines with 'at' "
    "replaces one line, 'at' plus 'end' replaces the inclusive block, 'after' "
    "inserts below a line, and an empty 'new' deletes. A stale anchor is refused, "
    "so you never repeat a line's full text and never land on the wrong line. To "
    "change several files or spots at once, use edit_plan with an 'ops' list: one "
    "all-or-nothing batch, refused whole if any anchor is stale. apply_diff applies "
    "a unified diff to one file and is refused whole if any hunk's context does not "
    "match exactly. Use edit_file (its 'old' text must be unique) when you did not "
    "take a hashed read. After you receive the tool results, continue. When you have "
    "the final answer and need no more tools, reply with the answer and DO NOT emit "
    "any TOOL line. Keep tool use minimal."
)
