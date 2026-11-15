"""Advisory edit-time check for agent harnesses that run PostToolUse hooks.

Claude Code and Codex can run a command after the model writes or edits a file.
This module reads that hook event on stdin and, for prose files, returns two
kinds of advisory context to the model:

- preservation: when the event carries the text before and after an edit, the
  meaning comparison names numbers, links, quotes, citations, modals, scope
  words, negations and names that the edit dropped, added or changed;
- style: the detector's HIGH and MEDIUM findings in the new text. Words inside
  quotation marks and Markdown block quotes belong to the person quoted, so the
  style check skips them and says how many findings it left out.

It reads only the event on stdin. It opens no file, starts no program, opens no
network connection and writes nothing but its answer on stdout. It never blocks
the edit: the exit status is always 0, and an event it cannot use produces no
output. A finding is advice to the model. It does not prove that meaning changed
or that the edit is wrong; a change the user asked for is expected to show up.

Set ARTICULATE_EDIT_HOOK=off in the environment to turn the hook off. Set
ARTICULATE_EDIT_HOOK_QUOTES=check to check quoted words as well.
"""
import json
import os
import re
import sys

from . import checkext, masking, meaning

PROSE_SUFFIXES = frozenset((".md", ".markdown", ".mdx", ".txt", ".text", ".rst",
                            ".adoc", ".asciidoc", ".tex"))
MAX_EVENT_BYTES = 4 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_STYLE = 5
MAX_PRESERVATION = 6
# A changed code block or quote is named with its whole text, which can run to
# the size of the edit. Each note and the whole answer are clipped so one edit
# cannot flood the model's context with a copy of the file.
MAX_NOTE_CHARS = 240
MAX_CONTEXT_CHARS = 6000
EVENT = "PostToolUse"
_PATCH_FILE = re.compile(r"^\*\*\* (Add|Update|Delete) File: (.+?)\s*$")
_PATCH_MOVE = re.compile(r"^\*\*\* Move to: (.+?)\s*$")
_BLOCK_QUOTE = re.compile(r"^([ \t]{0,3}(?:>[ \t]?)+)(.*?)(\r?\n)?$", re.S)
ADVICE_NOTE = ("These notes are advice from a word-level comparison. A change the user "
                  "asked for will appear here too.")


def is_prose(path):
    return isinstance(path, str) and os.path.splitext(path)[1].lower() in PROSE_SUFFIXES


def _claude_changes(name, tool_input):
    """Changes from Claude Code's Write, Edit and MultiEdit tool input."""
    path = tool_input.get("file_path")
    if name == "Write" and isinstance(tool_input.get("content"), str):
        return [(path, None, tool_input["content"])]
    if name == "Edit":
        edits = [tool_input]
    elif name == "MultiEdit" and isinstance(tool_input.get("edits"), list):
        edits = tool_input["edits"]
    else:
        return []
    return [(path, e.get("old_string"), e.get("new_string")) for e in edits
            if isinstance(e, dict) and isinstance(e.get("old_string"), str)
            and isinstance(e.get("new_string"), str)]


def _patch_text(command):
    """The apply_patch body from Codex tool input, which may be a string or argv."""
    if isinstance(command, str):
        return command
    if isinstance(command, list):
        for part in reversed(command):
            if isinstance(part, str) and "*** Begin Patch" in part:
                return part
    return None


def parse_patch(patch):
    """(path, old, new) for each added or updated file in a Codex apply_patch body.

    An added file has no old text. An updated file's old text is its context and
    removed lines; its new text is its context and added lines, hunk by hunk.
    """
    changes, current = [], None
    for line in patch.splitlines():
        head = _PATCH_FILE.match(line)
        if head:
            kind, path = head.groups()
            current = None if kind == "Delete" else {"path": path, "add": kind == "Add",
                                                     "old": [], "new": []}
            if current is not None:
                changes.append(current)
            continue
        move = _PATCH_MOVE.match(line)
        if move and current is not None:
            current["path"] = move.group(1)
            continue
        if current is None or line.startswith(("***", "@@")):
            continue
        mark, body = line[:1], line[1:]
        if mark in (" ", "-") and not current["add"]:
            current["old"].append(body)
        if mark in (" ", "+"):
            current["new"].append(body)
    return [(c["path"], None if c["add"] else "\n".join(c["old"]), "\n".join(c["new"]))
            for c in changes]


def changes_from_event(event):
    """Every (path, old, new) prose change the hook event describes."""
    if not isinstance(event, dict) or event.get("hook_event_name") not in (None, EVENT):
        return []
    name, tool_input = event.get("tool_name"), event.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    if name == "apply_patch":
        patch = _patch_text(tool_input.get("command") or tool_input.get("patch"))
        found = parse_patch(patch) if patch else []
    else:
        found = _claude_changes(name, tool_input)
    return [(path, old, new) for path, old, new in found
            if is_prose(path) and isinstance(new, str) and len(new) <= MAX_TEXT_CHARS
            and (old is None or len(old) <= MAX_TEXT_CHARS)]


def clip(text, limit=MAX_NOTE_CHARS):
    """Text cut to limit characters, with the number of characters left out."""
    if len(text) <= limit:
        return text
    return "%s... (%d more characters)" % (text[:limit], len(text) - limit)


def preservation_notes(old, new, is_tex=False):
    if old is None or old == new:
        return []
    rows = meaning.blocking(meaning.compare(old, new, tex=is_tex))
    return [clip(meaning.describe_item(r)) for r in rows[:MAX_PRESERVATION]] + (
        ["and %d more" % (len(rows) - MAX_PRESERVATION)] if len(rows) > MAX_PRESERVATION else [])


def _mask_line(line):
    """One line with quoted words blanked to spaces of the same length.

    A Markdown block quote keeps its ">" markers and loses its text. Elsewhere the
    detector's own quote mask blanks double-quoted and curly-quoted spans.
    Straight single quotes stay, because an apostrophe would open a false span.
    Lengths never change, so line numbers and offsets still point at the text.
    """
    block = _BLOCK_QUOTE.match(line)
    if block and block.group(1).strip():
        marks, body, end = block.group(1), block.group(2), block.group(3) or ""
        return marks + " " * len(body) + end
    return masking.mask_quoted(line)


def mask_quotations(text):
    """The text with every quotation blanked, line by line, at the same length."""
    return "".join(_mask_line(line) for line in text.splitlines(keepends=True))


def quotes_checked():
    return os.environ.get("ARTICULATE_EDIT_HOOK_QUOTES", "").strip().lower() == "check"


def _hits(text):
    result = checkext.check_text(text)
    return sorted(result["high"] + result["medium"], key=lambda h: h["start"])


def _inside_count(new, masked):
    """How many findings in the unmasked text start on a blanked character."""
    return sum(1 for h in _hits(new)
               if h["start"] < len(masked) and masked[h["start"]] != new[h["start"]])


def style_notes(new):
    """Style findings in the new text, quoted words left out unless asked for."""
    if quotes_checked():
        hits, skipped = _hits(new), 0
    else:
        masked = mask_quotations(new)
        hits = _hits(masked)
        skipped = _inside_count(new, masked) if masked != new else 0
    # A finding's match is read from the original text, so a quote mark that
    # sits next to a finding is shown as written.
    notes = [clip("L%d %s %r" % (h["line"], h["label"], new[h["start"]:h["end"]]))
             for h in hits[:MAX_STYLE]]
    if len(hits) > MAX_STYLE:
        notes.append("and %d more" % (len(hits) - MAX_STYLE))
    if skipped:
        notes.append("%d inside quotation marks or block quotes left out" % skipped)
    return notes


def review(event):
    """The advisory text for one hook event, or None when there is nothing to say."""
    blocks = []
    for path, old, new in changes_from_event(event):
        is_tex = path.lower().endswith(".tex")
        kept = preservation_notes(old, new, is_tex)
        style = style_notes(new)
        if not kept and not style:
            continue
        lines = ["Articulate, %s:" % os.path.basename(path)]
        if kept:
            lines.append("  possible meaning change in this edit (lines count within the "
                         "edited text): " + "; ".join(kept))
        if style:
            lines.append("  style findings in the new text: " + "; ".join(style))
        blocks.append("\n".join(lines))
    if not blocks:
        return None
    body = "\n".join(blocks)
    if len(body) > MAX_CONTEXT_CHARS:
        body = body[:MAX_CONTEXT_CHARS] + "\n... (%d more characters of findings left out)" % (
            len(body) - MAX_CONTEXT_CHARS)
    return body + "\n" + ADVICE_NOTE


def respond(raw):
    """The JSON a PostToolUse hook prints for raw stdin bytes, or None."""
    if os.environ.get("ARTICULATE_EDIT_HOOK", "").strip().lower() in ("off", "0", "false"):
        return None
    if len(raw) > MAX_EVENT_BYTES:
        raise ValueError("hook event is %d bytes, over the %d byte limit" % (len(raw), MAX_EVENT_BYTES))
    text = review(json.loads(raw.decode("utf-8")))
    if text is None:
        return None
    return json.dumps({"hookSpecificOutput": {"hookEventName": EVENT,
                                              "additionalContext": text}})


def main(stdin=None, stdout=None, stderr=None):
    """Run once as a hook command. Always returns 0 so the edit is never blocked."""
    stdin = stdin or sys.stdin.buffer
    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr
    try:
        answer = respond(stdin.read(MAX_EVENT_BYTES + 1))
    except Exception as exc:  # advisory hook: report the failure, never block the edit
        stderr.write("articulate edit hook skipped this event: %s: %s\n" % (type(exc).__name__, exc))
        return 0
    if answer is not None:
        stdout.write(answer + "\n")
        stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
