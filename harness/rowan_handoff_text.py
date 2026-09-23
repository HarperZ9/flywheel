"""rowan_handoff_text.py -- what may leave the machine in a handoff brief.

The brief is copied to the clipboard and pasted into another provider's agent,
so every free-text field passes through here first. Credentials are replaced
by a marker, the workspace root by `<workspace>`, any other host path by a
marker, a model's TOOL lines by the tool name and path, and long text is cut
with a stated marker. A line that still looks like a credential after that is
withheld whole.

The redaction is a pattern list. It catches URL user info, password flags,
`sshpass -p`, keyword-and-value pairs such as `password hunter2pass`, and the
shapes the engine's secret scanners already know. A credential written some
other way passes, which is why the brief lists REDACTION_IS_PATTERN_BASED in
what it does not prove. Standard library and engine scanners only.
"""
from __future__ import annotations

import re

from .bundle import scan_for_secrets
from .continuation_context import _BEARER, _CREDENTIAL_ASSIGNMENT, scrub_credentials

OMITTED = "[credential omitted]"
WITHHELD = "[line withheld: credential pattern]"
HOST_PATH = "[host path omitted]"

_VALUE = r"('[^'\n]*'|\"[^\"\n]*\"|\S+)"
_URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
_PASSWORD_FLAG = re.compile(r"(?i)(--password)(=|\s+)" + _VALUE)
_SSHPASS = re.compile(r"(?i)\b(sshpass\s+-p)\s*" + _VALUE)
_MYSQL_P = re.compile(r"(?i)\b((?:mysql|mariadb)[\w-]*\b[^\n]*?\s-p)(?=[^\s-])(\S+)")
# A keyword, a space, then a value that looks like a credential: quoted, or
# at least 8 characters with a digit or a symbol, so "token limit" survives.
_KEYWORD_VALUE = re.compile(
    r"(?i)\b(\w*(?:password|passwd|secret(?:_access_key)?|api[ _-]?key|access[ _-]?key"
    r"|token))(\s+)('[^'\n]+'|\"[^\"\n]+\"|(?=\S*[\d/+=!@#$%^&*])\S{8,})")
_DRIVE_PATH = re.compile(r"(?<![\w/\\])[A-Za-z]:[\\/][^\s'\"`<>|]*")
_POSIX_HOST = re.compile(
    r"(?<![\w.~/\\])/(?:Users|home|root|tmp|var|etc|mnt|private|opt|srv|Volumes)"
    r"(?:/[^\s'\"`<>|]*)?")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def redact(text) -> str:
    """Replace every credential shape named above with a marker."""
    value = scrub_credentials(str(text or ""))
    value = _URL_USERINFO.sub(lambda m: m.group(1) + OMITTED + "@", value)
    value = _PASSWORD_FLAG.sub(lambda m: m.group(1) + m.group(2) + OMITTED, value)
    value = _SSHPASS.sub(lambda m: m.group(1) + " " + OMITTED, value)
    value = _MYSQL_P.sub(lambda m: m.group(1) + OMITTED, value)
    return _KEYWORD_VALUE.sub(lambda m: m.group(1) + m.group(2) + OMITTED, value)


def _root_pattern(root):
    parts = [p for p in re.split(r"[\\/]+", str(root or "")) if p]
    if len(parts) < 2:
        return None
    lead = "/" if str(root).startswith("/") else ""
    return re.compile(re.escape(lead) + r"[\\/]+".join(map(re.escape, parts))
                      + r"(?![^\\/\s'\"`])", re.IGNORECASE)


def host_safe(text, root=None) -> str:
    """The workspace root becomes `<workspace>`; any other host path a marker."""
    value = str(text or "")
    pattern = _root_pattern(root)
    if pattern is not None:
        value = pattern.sub("<workspace>", value)
    value = _DRIVE_PATH.sub(HOST_PATH, value)
    return _POSIX_HOST.sub(HOST_PATH, value)


def leaks(line: str) -> bool:
    """A rendered line that still carries a credential shape."""
    if scan_for_secrets(line):
        return True
    return any("[credential" not in m.group(0)
               for pattern in (_CREDENTIAL_ASSIGNMENT, _BEARER) for m in pattern.finditer(line))


def outbound(text, root=None) -> str:
    """Free text as it may leave: redacted, host paths replaced."""
    return host_safe(redact(text), root)


def one_line(text, limit: int = 200) -> str:
    flat = " ".join(str(text or "").split())
    flat = _CONTROL.sub(lambda m: "\\x%02x" % ord(m.group(0)), flat)
    return flat if len(flat) <= limit else flat[:limit - 3] + "..."


def code(text, root=None, limit: int = 200) -> str:
    """A path or command as one inline code span: nothing in it can start a
    new Markdown line or close the span."""
    return "`" + one_line(outbound(text, root), limit).replace("`", "'") + "`"


def quote(text, root=None, *, max_lines: int = 60, max_chars: int = 8_000,
          line_chars: int = 2_000) -> str:
    """A block quote of at most `max_lines` lines and `max_chars` characters.
    What is cut is counted in a closing marker, never dropped silently."""
    lines = outbound(text, root).strip().splitlines() or ["(empty)"]
    kept, used = [], 0
    for line in lines[:max_lines]:
        room = min(line_chars, max_chars - used)
        if room <= 0:
            break
        kept.append(line[:room])
        used += len(kept[-1])
    omitted_lines = len(lines) - len(kept)
    omitted_chars = sum(map(len, lines)) - used
    body = [WITHHELD if leaks(line) else line for line in kept]
    out = "\n".join("> " + line for line in body)
    if omitted_lines or omitted_chars:
        out += (f"\n> [{omitted_lines} more lines and {omitted_chars} more characters "
                "are in the private trace]")
    return out


def safe_line(line: str) -> str:
    """One rendered brief line, withheld whole if a credential shape survived."""
    return WITHHELD if leaks(line) else line
