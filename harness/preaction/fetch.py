"""fetch.py -- is this call a read-only fetch the owner's fetch hosts may admit?

The owner's fetch allowlist (owner.py) exempts documentation reads from rule
egress/002. The exemption is narrow on purpose. It applies only when the call
reads and sends nothing: WebFetch-style tools, or a single curl, wget or
Invoke-WebRequest command with no upload, method, credential, header or
config flag, no output path outside the working directory, no shell
metacharacters, and URLs whose query and fragment stay short and carry no
user:password part. Option prefixes count: GNU wget and PowerShell accept an
unambiguous prefix of a long option, and curl and wget accept clustered short
options, so both forms are checked. HTTPie-style clients are not exempt at
all: they send data through bare key=value items. A long query string is how a GET request carries data
out, so it loses the exemption.

Pure: same call, same answer. The rule pack names this check through the
match key read_only_fetch_hosts, so a change here changes the pack digest only
when the pack text changes; the module docstring and tests pin the behavior.
"""
from __future__ import annotations

import shlex
from urllib.parse import urlsplit

from .normalize import _URL, Facts

MAX_QUERY_CHARS = 128
_POSIX_CMDS = {"curl", "wget"}
_PS_CMDS = {"iwr", "invoke-webrequest", "irm", "invoke-restmethod"}
_META = ("|", ";", "&", ">", "<", "`", "$(", "\n", "\r")
# Long options that send data, change the method, carry credentials or
# headers, read a config or input file, or route through a proxy. GNU wget
# accepts any unambiguous prefix of a long option, so a prefix of one of
# these (four characters or more) counts too.
_SEND_LONG = (
    "--data", "--data-raw", "--data-binary", "--data-urlencode", "--data-ascii", "--json",
    "--form", "--form-string", "--upload-file", "--request", "--user", "--header", "--cookie",
    "--config", "--referer", "--post-data", "--post-file", "--method", "--body-data",
    "--body-file", "--password", "--http-user", "--http-password", "--input-file", "--proxy",
    "--proxy-user", "--netrc", "--oauth2-bearer", "--aws-sigv4", "--cert", "--cookie-jar",
    "--execute", "--load-cookies", "--use-askpass")
_OUTPUT_LONG = ("--output", "--output-document", "--directory-prefix")
# curl and wget short options with the same effect, case-sensitive. Short
# options can be clustered (-sLd@x), so every letter of a cluster is checked.
_SEND_SHORT = set("dFTXxuUHbKeEcni")
_OUTPUT_SHORT = set("oOP")
# PowerShell parameters; PowerShell accepts any unambiguous prefix.
_PS_SEND = ("-method", "-body", "-infile", "-headers", "-credential", "-websession", "-form",
            "-usedefaultcredentials", "-token", "-authentication", "-proxy", "-proxycredential",
            "-certificate", "-custommethod", "-sessionvariable", "-contenttype")
_PS_OUTPUT = ("-outfile",)


def _bad_output_path(value: str) -> bool:
    v = value.strip().strip("'\"").replace("\\", "/")
    return (v.startswith(("/", "~")) or ".." in v.split("/")
            or (len(v) > 1 and v[1] == ":"))


def _prefix_of(name: str, options: tuple, minimum: int) -> bool:
    return len(name) >= minimum and any(o.startswith(name) for o in options)


def _value(tokens: list, i: int, tok: str) -> str:
    if "=" in tok:
        return tok.split("=", 1)[1]
    return tokens[i + 1] if i + 1 < len(tokens) else ""


def _posix_flags_ok(tokens: list) -> bool:
    for i, tok in enumerate(tokens[1:], start=1):
        if tok.startswith("@"):
            return False
        if tok.startswith("--"):
            name = tok.split("=", 1)[0]
            if _prefix_of(name, _SEND_LONG, 4):
                return False
            if _prefix_of(name, _OUTPUT_LONG, 5) and _bad_output_path(_value(tokens, i, tok)):
                return False
        elif tok.startswith("-") and len(tok) > 1:
            cluster = tok[1:]
            for j, ch in enumerate(cluster):
                if ch in _SEND_SHORT:
                    return False
                if ch in _OUTPUT_SHORT:
                    rest = cluster[j + 1:]
                    value = rest if rest else (tokens[i + 1] if i + 1 < len(tokens) else "")
                    if _bad_output_path(value):
                        return False
                    break
                if not ch.isalpha():
                    break
    return True


def _ps_flags_ok(tokens: list) -> bool:
    for i, tok in enumerate(tokens[1:], start=1):
        if tok.startswith("@"):
            return False
        if not tok.startswith("-"):
            continue
        name = tok.split(":", 1)[0].lower()
        if _prefix_of(name, _PS_SEND, 3):
            return False
        if _prefix_of(name, _PS_OUTPUT, 3) and _bad_output_path(_value(tokens, i, tok)):
            return False
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
    if head in _POSIX_CMDS:
        return _posix_flags_ok(tokens)
    if head in _PS_CMDS:
        return _ps_flags_ok(tokens)
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
