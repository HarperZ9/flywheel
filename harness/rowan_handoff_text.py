"""rowan_handoff_text.py -- what may leave the machine in a handoff brief.

The brief is copied to the clipboard and pasted into another provider's agent,
so every free-text field passes through here first. Credentials are replaced
by a marker (the patterns live in rowan_handoff_redact), the workspace root by
`<workspace>`, any other host path the patterns below name (drive, home and
system paths, UNC paths in either slash, file URIs, drive mounts and bare
server names) by a marker, a model's TOOL lines by the tool name and path, and
long text is cut with a stated marker. A line that still looks like a
credential after that is withheld whole.

Text is cut before it is redacted, with a margin past the cut, so the work is
bounded by what the brief can show. A credential of up to MARGIN characters
that the cut splits is left, in part, in the redacted window's last MARGIN
characters, so a window that stops short of the text shows only what ends a
margin before its own end. That holds when an earlier credential's marker is
far shorter than the credential it replaced. A one-line field widens its
window, up to 64 margins, when redaction shrinks it below the room it has to
fill. Standard library and engine scanners only.
"""
from __future__ import annotations

import re

from .rowan_handoff_redact import OMITTED, leaks, redact

__all__ = ["HOST_PATH", "MARGIN", "OMITTED", "WITHHELD", "code", "flat_line", "host_safe",
           "leaks", "one_line", "outbound", "quote", "redact", "safe_line"]

WITHHELD = "[line withheld: credential pattern]"
HOST_PATH = "[host path omitted]"
#: Characters redacted past a cut and then dropped with it.
MARGIN = 512
#: How far a one-line field's window may widen, in margins past its room.
_WIDEN = (1, 4, 16, 64)

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


def _shown(red: str, room: int, whole: bool) -> str:
    """What a redacted window may show: all of it when the window held the
    whole text, otherwise at most `room` characters that end a margin before
    the window's end, where a credential the cut split still sits in part."""
    return red if whole else red[:max(0, min(room, len(red) - MARGIN))]


def _head(text: str, root, room: int) -> tuple[str, bool]:
    """One line's redacted head for `room` characters, and whether the window
    held the whole line. The window widens while redaction leaves it short of
    the room plus a margin."""
    for widen in _WIDEN:
        end = room + MARGIN * widen
        red, whole = outbound(text[:end], root), end >= len(text)
        if whole or len(red) >= room + MARGIN:
            break
    return _shown(red, room, whole), whole


def flat_line(text, root=None, limit: int = 200) -> str:
    """Free text as one outbound line of at most `limit` characters. The cut
    is marked even when the shown head is shorter than the limit."""
    words = " ".join(str(text or "").split())
    shown, whole = _head(words, root, limit)
    head = one_line(shown, limit)
    if not whole and not head.endswith("..."):
        head = head[:limit - 3] + "..."
    return head


def code(text, root=None, limit: int = 200) -> str:
    """A path or command as one inline code span: nothing in it can start a
    new Markdown line or close the span."""
    return "`" + flat_line(text, root, limit).replace("`", "'") + "`"


def _window(lines: list, max_lines: int, max_chars: int, line_chars: int) -> list:
    """The raw lines a quote can show, each cut a margin past its share."""
    out, used = [], 0
    for line in lines[:max_lines]:
        room = min(line_chars, max_chars - used)
        if room <= 0:
            break
        out.append(line[:room + MARGIN])
        used += min(len(line), room)
    return out


def quote(text, root=None, *, max_lines: int = 60, max_chars: int = 8_000,
          line_chars: int = 2_000) -> str:
    """A block quote of at most `max_lines` lines and `max_chars` characters.
    What is cut is counted in a closing marker, never dropped silently."""
    raw = str(text or "").strip().splitlines() or ["(empty)"]
    window = _window(raw, max_lines, max_chars, line_chars)
    lines = outbound("\n".join(window), root).split("\n")
    # Redaction keeps line breaks. Were one lost, every line would count as cut.
    whole = ([len(w) == len(r) for w, r in zip(window, raw)]
             if len(lines) == len(window) else [False] * len(lines))
    kept, used = [], 0
    for line, entire in zip(lines[:max_lines], whole):
        room = min(line_chars, max_chars - used)
        if room <= 0:
            break
        kept.append(_shown(line, room, entire)[:room])
        used += len(kept[-1])
    omitted_lines = len(raw) - len(kept)
    # The shown part counts as redacted; the rest as it sits in the trace.
    omitted_chars = (sum(map(len, lines)) - used
                     + sum(map(len, raw)) - sum(map(len, window)))
    body = [WITHHELD if leaks(line) else line for line in kept]
    out = "\n".join("> " + line for line in body)
    if omitted_lines or omitted_chars:
        out += (f"\n> [{omitted_lines} more lines and {omitted_chars} more characters "
                "are in the private trace]")
    return out


def safe_line(line: str) -> str:
    """One rendered brief line, withheld whole if a credential shape survived."""
    return WITHHELD if leaks(line) else line
