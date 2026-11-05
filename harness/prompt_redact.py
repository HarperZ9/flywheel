"""prompt_redact -- strip local identifiers from text before it reaches a hosted model.

A hosted model reads every byte of a prompt and every tool result. Most of
what identifies the person at the keyboard rides along by accident: the home
folder in a path, the login name, the machine name, an email address, a key
pasted from a terminal. This filter swaps each for a stable placeholder so the
model can still reason about structure:

    the home folder (any separator)   ~
    the login name                    USER
    the machine name                  HOST
    an email address                  EMAIL-1, EMAIL-2, ...
    a deny-list match                 ID-1, ID-2, ...
    a credential                      [REDACTED:<rule>:<tag>] (trace_redact catalog)

The same value gets the same placeholder within one call. RFC 2606 and RFC
6761 names and noreply addresses are left alone. The report carries counts per
category, never a matched value.

The deny list is an untracked file of regexes, one per line, the same format
the publish metadata check reads. It comes from --deny-list, then
FLYWHEEL_REDACT_DENYLIST, then PUBLISH_DENYLIST, then
~/.flywheel/redact-denylist.txt.

Two entry points:

    python -m harness.prompt_redact filter [--deny-list F] < in > out
    python -m harness.prompt_redact hook   [--deny-list F]   (Claude Code UserPromptSubmit)

The hook reads the hook JSON on stdin. A prompt with no finding passes
silently. A prompt with a finding is blocked before it is sent, and the block
reason, which the user sees and the model does not, carries the redacted copy
to resubmit. A UserPromptSubmit hook can block a prompt or add context; it
cannot rewrite the prompt, so blocking is the only way to keep the original
text out of the request.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
import socket
import sys
from collections import Counter
from pathlib import Path

from .trace_redact import redact_text
from .trace_redact_rules import credential_rules

EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}")
ALLOWED_EMAIL = re.compile(
    r"(?i)@(?:[a-z0-9.-]+\.)?(?:example(?:\.(?:com|org|net))?|invalid|test|localhost)$|"
    r"@users\.noreply\.github\.com$|^noreply@|^no-reply@")
# Any user folder, not only this machine's: a path copied from elsewhere names
# its owner too.
USER_DIR = re.compile(r"(?i)\b[a-z]:[\\/]+users[\\/]+[^\\/\s\"'`]+|(?<![\w.])/(?:home|Users)/[^/\s\"'`]+")
GENERIC_NAMES = {"user", "users", "admin", "root", "runner", "localhost", "ubuntu", "build",
                 "docker", "github", "home", "test"}
DENY_ENV = ("FLYWHEEL_REDACT_DENYLIST", "PUBLISH_DENYLIST")
DEFAULT_DENY = Path.home() / ".flywheel" / "redact-denylist.txt"


def deny_patterns(path: str | None = None) -> list[re.Pattern]:
    """Regexes from the untracked deny list; a named file that is missing is an error."""
    named = path or next((os.environ[k] for k in DENY_ENV if os.environ.get(k)), None)
    target = Path(named) if named else DEFAULT_DENY
    if not target.is_file():
        if named:
            raise FileNotFoundError(f"prompt_redact: deny list not found: {target}")
        return []
    out = []
    for raw in target.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw and not raw.startswith("#"):
            out.append(re.compile(raw, re.I))
    return out


def _word(value: str) -> re.Pattern | None:
    value = value.strip()
    if len(value) < 3 or value.lower() in GENERIC_NAMES:
        return None
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(value) + r"(?![A-Za-z0-9])", re.I)


class Redactor:
    """One redaction pass configuration. Placeholders are stable per call."""

    def __init__(self, *, deny=None, home: str | None = None, user: str | None = None,
                 hosts=None, credentials: bool = True):
        self.deny = list(deny or [])
        home = home if home is not None else str(Path.home())
        parts = [p for p in re.split(r"[\\/]+", home or "") if p]
        lead = r"[\\/]+" if (home or "")[:1] in ("/", "\\") else ""
        self.home = re.compile(lead + r"[\\/]+".join(map(re.escape, parts)) + r"(?![A-Za-z0-9])",
                               re.I) if len(parts) >= 2 else None
        try:
            login = user if user is not None else getpass.getuser()
        except (OSError, KeyError):
            login = ""
        self.user = _word(login)
        names = hosts if hosts is not None else {socket.gethostname(),
                                                 os.environ.get("COMPUTERNAME", "")}
        self.hosts = [p for p in (_word(h) for h in names if h) if p]
        self.credentials = credentials

    def redact(self, text: str) -> tuple[str, dict]:
        """Return (redacted text, counts per category)."""
        counts: Counter = Counter()
        if self.credentials:
            text, found = redact_text(text, key=secrets.token_bytes(32), rules_=credential_rules())
            counts["credential"] += sum(found.values())
        text = self._numbered(text, self.deny, "ID", "deny-list", counts)
        text = self._numbered(text, [EMAIL], "EMAIL", "email", counts, ALLOWED_EMAIL)
        for rx, token, cat in ([(self.home, "~", "home-path")] if self.home else []) + \
                [(USER_DIR, "~", "home-path")] + \
                ([(self.user, "USER", "user-name")] if self.user else []) + \
                [(h, "HOST", "machine-name") for h in self.hosts]:
            text, n = rx.subn(token, text)
            counts[cat] += n
        return text, {k: v for k, v in sorted(counts.items()) if v}

    @staticmethod
    def _numbered(text, patterns, prefix, cat, counts, allow=None):
        seen: dict[str, str] = {}

        def swap(m):
            value = m.group(0)
            if allow is not None and allow.search(value):
                return value
            key = value.lower()
            if key not in seen:
                seen[key] = f"{prefix}-{len(seen) + 1}"
            counts[cat] += 1
            return seen[key]

        for rx in patterns:
            text = rx.sub(swap, text)
        return text


def hook_response(event: dict, redactor: Redactor) -> dict | None:
    """The UserPromptSubmit reply: None to pass, or a block carrying the redacted copy."""
    prompt = event.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        return None
    clean, counts = redactor.redact(prompt)
    if not counts:
        return None
    found = ", ".join(f"{k} {v}" for k, v in counts.items())
    return {"decision": "block",
            "reason": ("prompt_redact held this prompt back: it names local identifiers "
                       f"({found}). Resubmit the redacted copy below, or remove the hook "
                       "for this session if the task needs the real values.\n\n" + clean)}


def main(argv=None, stdin=None, stdout=None, stderr=None) -> int:
    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    ap = argparse.ArgumentParser(prog="python -m harness.prompt_redact",
                                 description="Strip local identifiers before text reaches a hosted model.")
    ap.add_argument("mode", choices=("filter", "hook"))
    ap.add_argument("--deny-list", help="untracked file of private regexes, one per line")
    ap.add_argument("--no-credentials", action="store_true", help="skip the credential catalog")
    a = ap.parse_args(argv)
    try:
        redactor = Redactor(deny=deny_patterns(a.deny_list), credentials=not a.no_credentials)
    except (FileNotFoundError, re.error) as exc:
        print(f"prompt_redact: {exc}", file=stderr)
        return 2
    raw = stdin.read()
    if a.mode == "filter":
        clean, counts = redactor.redact(raw)
        stdout.write(clean)
        print(json.dumps({"prompt_redact": counts}), file=stderr)
        return 0
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"prompt_redact: hook input is not JSON: {exc}", file=stderr)
        return 2
    reply = hook_response(event, redactor)
    if reply:
        stdout.write(json.dumps(reply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
