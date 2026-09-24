"""rowan_handoff_text.py -- what may leave the machine in a handoff brief.

The brief is copied to the clipboard and pasted into another provider's agent,
so every free-text field passes through here first. Credentials are replaced
by a marker (the patterns live in rowan_handoff_redact), the workspace root by
`<workspace>`, any other host path the patterns below name (drive, home and
system paths, UNC paths in either slash, file URIs, drive mounts and bare
server names) by a marker, a model's TOOL lines by the tool name and path, and
long text is cut with a stated marker. A line that still looks like a
credential after that is withheld whole.

Each field is redacted whole and cut after, so a credential the cut splits is
replaced whole, however long it is, and a pattern bound to one line still sees
that line. A quote reads whole lines only. A credential that runs past the
last line read either matches to the end of what was read, as a private key
block or an open quoted value does, or holds its secret past that line, where
nothing is shown. The patterns run in time that grows with the text, and no
field reads more than REDACT_CHARS: a longer one-line field, or a quote line
that would pass the bound, stays in the private trace and the brief says so.
Standard library and engine scanners only.
"""
from __future__ import annotations

import re

from .rowan_handoff_redact import OMITTED, leaks, redact

__all__ = ["HOST_PATH", "OMITTED", "REDACT_CHARS", "WITHHELD", "code", "flat_line",
           "host_safe", "leaks", "one_line", "outbound", "quote", "redact", "safe_line"]

WITHHELD = "[line withheld: credential pattern]"
HOST_PATH = "[host path omitted]"
#: The most characters of one field the brief reads and redacts.
REDACT_CHARS = 65_536

_DRIVE_PATH = re.compile(r"(?<![\w/\\])[A-Za-z]:[\\/][^\s'\"`<>|]*")
# \\server\share, \\?\C:\..., \\wsl$\distro, and the same with JSON's doubled
# backslashes.
_UNC_PATH = re.compile(r"(?<![\w\\])\\{2,4}[\w.$?-]+\\[^\s'\"`<>|]*")
# A bare \\fileserver01 or \\10.0.0.5. The name must hold a digit, a dot, a
# hyphen or a $, so a LaTeX \\hline or \\frac and a \\x41 escape stay text.
_UNC_HOST = re.compile(r"(?<![\w\\])\\{2,4}(?!(?:x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4})(?![\w.$-]))"
                       r"(?=[\w.$-]*[\d.$-])[A-Za-z0-9][\w.$-]*(?![\w.$\\-])")
# //server/share, the forward-slash UNC form. A URL's // follows a colon.
_SLASH_UNC = re.compile(r"(?<![\w:/\\.])//[\w.$-]+/[^\s'\"`<>|]*")
# file://server/share and file:///C:/..., unless it names the workspace.
_FILE_URI = re.compile(r"(?i)\bfile:/{2,}(?!/*<workspace>)[^\s'\"`<>|]*")
# /c/Users/..., the drive form of MSYS, Git Bash and WSL-style shells.
_DRIVE_MOUNT = re.compile(r"(?<![\w.~/\\:-])/[A-Za-z]/[^\s'\"`<>|]*")
_POSIX_HOST = re.compile(
    r"(?<![\w.~/\\])/(?:Users|home|root|tmp|var|etc|mnt|private|opt|srv|Volumes"
    r"|cygdrive)(?:/[^\s'\"`<>|]*)?")
_HOST_PATHS = (_FILE_URI, _UNC_PATH, _UNC_HOST, _SLASH_UNC, _DRIVE_PATH, _DRIVE_MOUNT,
               _POSIX_HOST)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _root_pattern(root):
    parts = [p for p in re.split(r"[\\/]+", str(root or "")) if p]
    if len(parts) < 2:
        return None
    lead = r"[\\/]+" if str(root)[:1] in "\\/" else ""
    return re.compile(lead + r"[\\/]+".join(map(re.escape, parts))
                      + r"(?![^\\/\s'\"`])", re.IGNORECASE)


def host_safe(text, root=None) -> str:
    """The workspace root becomes `<workspace>`; any other host path a marker."""
    value = str(text or "")
    pattern = _root_pattern(root)
    if pattern is not None:
        value = pattern.sub("<workspace>", value)
    for path in _HOST_PATHS:
        value = path.sub(HOST_PATH, value)
    return value


def outbound(text, root=None) -> str:
    """Free text as it may leave: redacted, host paths replaced."""
    return host_safe(redact(text), root)


def one_line(text, limit: int = 200) -> str:
    flat = " ".join(str(text or "").split())
    flat = _CONTROL.sub(lambda m: "\\x%02x" % ord(m.group(0)), flat)
    return flat if len(flat) <= limit else flat[:limit - 3] + "..."


def flat_line(text, root=None, limit: int = 200) -> str:
    """Free text as one outbound line of at most `limit` characters.

    The text is redacted with its line breaks, then flattened and cut, so a
    pattern bound to one line still sees it. A text past REDACT_CHARS is not
    read, and the line says how long it is and where it stays."""
    value = str(text or "")
    if len(value) > REDACT_CHARS:
        return one_line(f"[{len(value)} characters left in the private trace: "
                        "longer than the brief redacts]", limit)
    return one_line(outbound(value, root), limit)


def code(text, root=None, limit: int = 200) -> str:
    """A path or command as one inline code span: nothing in it can start a
    new Markdown line or close the span."""
    return "`" + flat_line(text, root, limit).replace("`", "'") + "`"


def _window(lines: list, max_lines: int) -> list:
    """The lines a quote reads: whole lines, at most `max_lines` of them and
    REDACT_CHARS in all, so no credential is split before it is redacted."""
    out, size = [], -1
    for line in lines[:max_lines]:
        size += len(line) + 1
        if size > REDACT_CHARS:
            break
        out.append(line)
    return out


def quote(text, root=None, *, max_lines: int = 60, max_chars: int = 8_000,
          line_chars: int = 2_000) -> str:
    """A block quote of at most `max_lines` lines and `max_chars` characters.
    What is cut is counted in a closing marker, never dropped silently."""
    raw = str(text or "").strip().splitlines() or ["(empty)"]
    window = _window(raw, max_lines)
    lines = outbound("\n".join(window), root).split("\n") if window else []
    kept, used = [], 0
    for line in lines[:max_lines]:
        room = min(line_chars, max_chars - used)
        if room <= 0:
            break
        kept.append(line[:room])
        used += len(kept[-1])
    omitted_lines = len(lines) - len(kept) + len(raw) - len(window)
    # What the quote read counts as redacted; the rest as it sits in the trace.
    omitted_chars = sum(map(len, lines)) - used + sum(map(len, raw[len(window):]))
    rows = ["> " + (WITHHELD if leaks(line) else line) for line in kept]
    if omitted_lines or omitted_chars:
        rows.append(f"> [{omitted_lines} more lines and {omitted_chars} more characters "
                    "are in the private trace]")
    return "\n".join(rows)


def safe_line(line: str) -> str:
    """One rendered brief line, withheld whole if a credential shape survived."""
    return WITHHELD if leaks(line) else line
