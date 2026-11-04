"""Text, fetch-code and git checks for check_publish_metadata.py. Stdlib only.

The patterns that ship here are generic: a local user folder, the workspace
drive path, and consumer mail domains. Personal addresses, the machine name and
anything else private come from places that never ship:

- the machine's own name, read at run time;
- the git global user.email, read at run time, unless it is a noreply address;
- an untracked deny list, one regex per line, from --deny-list, the
  PUBLISH_DENYLIST environment variable, or scripts/.publish-denylist.txt.

Findings never print the matched value, only its category and a label, so a CI
log does not republish what the check found.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
from pathlib import Path

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
GENERIC = [
    (re.compile(r"Users[\\/]+Zain\b", re.I), "local-path", "local user folder"),
    (re.compile(r"\bC:[\\/]+dev[\\/]+", re.I), "local-path", "workspace drive path"),
    (re.compile(r"[A-Za-z0-9._%+-]+@(?:gmail|googlemail|yahoo|ymail|proton(?:mail)?|pm|"
                r"outlook|hotmail|icloud|me|aol)\.(?:com|me|ch)\b", re.I),
     "personal-email", "consumer mail address"),
]
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".ps1", ".sh", ".rb", ".go", ".rs"}
# A line counts as fetch code when it names a User-Agent, puts mailto or email in
# a query string, or passes them as a call keyword or a mailto dict key. An
# href="mailto:..." link and an "email" field in fixture data do not.
FETCH_LINE = re.compile(
    r"(?i)user[-_ ]?agent|[?&](?:mailto|email)=|[(,]\s*(?:mailto|email)\s*=|"
    r"\bmailto\s*=\s*[\"']|[\"']mailto[\"']\s*:")
# RFC 2606 and RFC 6761 names, and noreply addresses, are never a person.
ALLOWED_ADDRESS = re.compile(
    r"(?i)@(?:[a-z0-9.-]+\.)?(?:example(?:\.(?:com|org|net))?|invalid|test|localhost)$|"
    r"@users\.noreply\.github\.com$|^noreply@|^no-reply@")
NOREPLY = re.compile(r"(?i)noreply|no-reply")
DEFAULT_DENY = Path(__file__).resolve().parent / ".publish-denylist.txt"
_GENERIC_NAMES = {"localhost", "runner", "ubuntu", "build", "docker", "github"}


def _git(args, cwd=None):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                           timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"check_publish_metadata: git {' '.join(args)} failed: {exc}")
        return None
    return r.stdout if r.returncode == 0 else None


def local_patterns(deny_list: str | None = None):
    """Private patterns gathered at run time. Labels never carry the value."""
    out = []
    for name in {os.environ.get("COMPUTERNAME", ""), socket.gethostname()}:
        name = name.strip()
        if len(name) >= 4 and name.lower() not in _GENERIC_NAMES:
            out.append((re.compile(r"\b" + re.escape(name) + r"\b", re.I),
                        "machine-name", "this machine's name"))
    mail = (_git(["config", "--global", "user.email"]) or "").strip()
    if mail and not NOREPLY.search(mail):
        out.append((re.compile(re.escape(mail), re.I), "personal-email", "git global user.email"))
    path = deny_list or os.environ.get("PUBLISH_DENYLIST") or DEFAULT_DENY
    path = Path(path)
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
        for n, raw in enumerate(lines, 1):
            raw = raw.strip()
            if raw and not raw.startswith("#"):
                out.append((re.compile(raw, re.I), "deny-list", f"deny list entry {n}"))
    elif deny_list:
        raise SystemExit(f"check_publish_metadata: deny list not found: {path}")
    return out


def check_text(text: str, suffix: str, patterns):
    """Return (line, category, detail) for every leak in one text file."""
    out, seen = [], set()
    is_code = suffix.lower() in CODE_EXT
    for lineno, line in enumerate(text.splitlines(), 1):
        for rx, cat, label in patterns:
            if rx.search(line) and (lineno, cat) not in seen:
                seen.add((lineno, cat))
                out.append((lineno, cat, label))
        if is_code and FETCH_LINE.search(line):
            for addr in EMAIL.findall(line):
                if not ALLOWED_ADDRESS.search(addr):
                    out.append((lineno, "fetch-header",
                                "an address in a User-Agent, mailto or email request field"))
                    break
    return out


def check_git(root: Path, rev_range: str):
    """Warn on commits whose author email is not a noreply address or whose
    offset is not UTC. rev_range 'unpushed' means commits on no remote."""
    if _git(["rev-parse", "--is-inside-work-tree"], cwd=root) is None:
        return []
    if rev_range == "unpushed":
        args = ["log", "--branches", "--not", "--remotes"]
    elif rev_range == "all":
        args = ["log", "HEAD"]
    else:
        args = ["log", rev_range]
    log = _git([*args, "--format=%h%x09%ae%x09%ad", "--date=format:%z"], cwd=root)
    if log is None:
        return []
    emails, offsets = {}, {}
    for row in log.splitlines():
        parts = row.split("\t")
        if len(parts) != 3:
            continue
        _sha, mail, offset = parts
        if not mail.lower().endswith("@users.noreply.github.com") and mail.lower() != "noreply@github.com":
            emails[mail] = emails.get(mail, 0) + 1
        if offset not in ("+0000", "-0000"):
            offsets[offset] = offsets.get(offset, 0) + 1
    out = []
    for i, (_mail, count) in enumerate(sorted(emails.items()), 1):
        out.append(("git-author", f"author email {i} is not a noreply address ({count} commits)"))
    for offset, count in sorted(offsets.items()):
        out.append(("git-timezone", f"offset {offset} on {count} commits"))
    return out
