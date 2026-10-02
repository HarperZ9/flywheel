"""fetch.py -- is this call a read-only fetch the owner's fetch hosts may admit?

The owner's fetch allowlist (owner.py) exempts documentation reads from rule
egress/002. The exemption is narrow on purpose. It applies only when the call
reads and sends nothing: WebFetch-style tools, or a single curl, wget or
Invoke-WebRequest command whose every option is on a short allowlist below,
whose every positional argument is an http or https URL, whose output path
stays inside the working directory, and whose URLs keep the query and
fragment short and carry no user:password part. A long query string is how a
GET request carries data out, so it loses the exemption.

The options are an allowlist, not a denylist. A denylist of sending options
was bypassed eight times in review: curl alone has options that route the
request to another address (--resolve, --connect-to, --socks5, --proxy1.0),
read a local file into the URL (--url-query, --variable), or write a file
anywhere (-D, --trace, --stderr). Any option not listed here, any prefix or
misspelling of one, and any shell expansion ($, backtick, %VAR%) loses the
exemption, and the call holds under egress/002 as it would with no fetch hosts.

Pure: same call, same answer. The rule pack names this check through the
match key read_only_fetch_hosts, so a change here changes the pack digest only
when the pack text changes; the module docstring and tests pin the behavior.
"""
from __future__ import annotations

import re
import shlex
from urllib.parse import urlsplit

from .normalize import _URL, Facts

MAX_QUERY_CHARS = 128
_META = ("|", ";", "&", ">", "<", "`", "$", "\n", "\r")
_NUM = re.compile(r"^[0-9]+(\.[0-9]+)?$")
_PATH, _COUNT = "path", "num"

# Per command: flags that take no value, and options that take one value of a
# checked kind. Long options take "--opt value" or "--opt=value".
_CURL = {
    "short_flags": set("sSLfIviNgO#"),
    "short_values": {"o": _PATH, "m": _COUNT},
    "long_flags": {"--silent", "--show-error", "--location", "--fail", "--fail-with-body",
                   "--head", "--verbose", "--include", "--compressed", "--no-progress-meter",
                   "--progress-bar", "--remote-name", "--create-dirs", "--http1.1", "--http2",
                   "--globoff", "--no-buffer"},
    "long_values": {"--output": _PATH, "--max-time": _COUNT, "--connect-timeout": _COUNT,
                    "--retry": _COUNT},
    "whole_tokens": set(),
}
_WGET = {
    "short_flags": set("qSNc"),
    "short_values": {"O": _PATH, "P": _PATH, "T": _COUNT, "t": _COUNT},
    "long_flags": {"--quiet", "--no-verbose", "--server-response", "--spider",
                   "--timestamping", "--continue", "--no-clobber"},
    "long_values": {"--output-document": _PATH, "--directory-prefix": _PATH,
                    "--timeout": _COUNT, "--tries": _COUNT, "--max-redirect": _COUNT},
    # wget spells some single options with two letters behind one dash.
    "whole_tokens": {"-nv", "-nc"},
}
_POSIX = {"curl": _CURL, "wget": _WGET}
_PS_CMDS = {"iwr", "invoke-webrequest", "irm", "invoke-restmethod"}
_PS_FLAGS = {"-usebasicparsing"}
_PS_VALUES = {"-uri": "url", "-outfile": _PATH, "-timeoutsec": _COUNT,
              "-maximumredirection": _COUNT}


def _is_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _safe_output_path(value: str) -> bool:
    """A relative path inside the working directory, with no hidden component
    (.claude, .codex, .git, .github and the like hold configuration) and no
    environment-variable expansion."""
    v = value.strip().strip("'\"").replace("\\", "/")
    if not v or v.startswith(("/", "~")) or (len(v) > 1 and v[1] == ":") or "%" in v:
        return False
    return not any(part == ".." or (part.startswith(".") and part != ".")
                   for part in v.split("/"))


def _value_ok(kind: str, value: str) -> bool:
    if kind == _PATH:
        return _safe_output_path(value)
    if kind == _COUNT:
        return bool(_NUM.match(value))
    return _is_url(value)


def _take(tokens: list, i: int, tok: str, name: str) -> tuple:
    """(value, tokens consumed) for an option at tokens[i]."""
    if tok != name:                       # --opt=value or an attached short value
        return tok[len(name):].lstrip("="), 1
    return (tokens[i + 1], 2) if i + 1 < len(tokens) else ("", 1)


def _short_cluster_ok(table: dict, tokens: list, i: int, tok: str) -> tuple:
    cluster = tok[1:]
    for j, ch in enumerate(cluster):
        if ch in table["short_flags"]:
            continue
        kind = table["short_values"].get(ch)
        if kind is None:
            return False, 1
        rest = cluster[j + 1:]
        if rest:
            return _value_ok(kind, rest), 1
        if i + 1 >= len(tokens):
            return False, 1
        return _value_ok(kind, tokens[i + 1]), 2
    return True, 1


def _posix_ok(table: dict, tokens: list) -> bool:
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in table["whole_tokens"] or tok in table["long_flags"]:
            i += 1
            continue
        if tok.startswith("--"):
            name = tok.split("=", 1)[0]
            kind = table["long_values"].get(name)
            if kind is None:
                return False
            value, step = _take(tokens, i, tok, name)
            if not _value_ok(kind, value):
                return False
            i += step
            continue
        if tok.startswith("-") and len(tok) > 1:
            ok, step = _short_cluster_ok(table, tokens, i, tok)
            if not ok:
                return False
            i += step
            continue
        if not _is_url(tok):
            return False                  # a bare host is fetched but never seen as a host
        i += 1
    return True


def _ps_ok(tokens: list) -> bool:
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if not tok.startswith("-"):
            if not _is_url(tok):
                return False
            i += 1
            continue
        name = tok.split(":", 1)[0].lower()
        if name in _PS_FLAGS:
            i += 1
            continue
        kind = _PS_VALUES.get(name)
        if kind is None:
            return False
        if ":" in tok:
            value, step = tok.split(":", 1)[1], 1
        else:
            value, step = (tokens[i + 1], 2) if i + 1 < len(tokens) else ("", 1)
        if not _value_ok(kind, value):
            return False
        i += step
    return True


def _command_is_read_only(command: str) -> bool:
    if any(m in command for m in _META):
        return False
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False
    if not tokens:
        return False
    head = tokens[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if head.endswith(".exe"):
        head = head[:-4]
    if head in _POSIX:
        return _posix_ok(_POSIX[head], tokens)
    if head in _PS_CMDS:
        return _ps_ok(tokens)
    return False


def _urls_are_quiet(text: str) -> bool:
    for m in _URL.finditer(text):
        if m.group(1):                      # user:password@host
            return False
        end = m.end()
        tail = text[end:].split(None, 1)[0] if text[end:].strip() else ""
        parts = urlsplit(m.group(0) + tail.strip("'\""))
        if len(parts.query) + len(parts.fragment) > MAX_QUERY_CHARS:
            return False
    return True


def read_only_fetch(facts: Facts) -> bool:
    """True when the call only reads from the network and sends nothing that
    could carry data out beyond a short query string."""
    if facts.kind == "web":
        return _urls_are_quiet(facts.text)
    if facts.kind == "exec" and facts.command:
        return _command_is_read_only(facts.command) and _urls_are_quiet(facts.command)
    return False
