"""fetch.py -- is this call a read-only fetch the owner's fetch hosts may admit?

The owner's fetch allowlist (owner.py) exempts documentation reads from rule
egress/002. The exemption is narrow on purpose. It applies only when the call
reads and sends nothing: WebFetch-style tools, or a single curl, wget or
Invoke-WebRequest command with no upload, method, credential, header or
config flag, no output path outside the working directory, no shell
metacharacters, and URLs whose query and fragment stay short and carry no
user:password part. A long query string is how a GET request carries data
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
_FETCH_CMDS = {"curl", "wget", "iwr", "invoke-webrequest", "irm", "invoke-restmethod",
               "http", "https", "xh"}
_META = ("|", ";", "&", ">", "<", "`", "$(", "\n", "\r")
# Flags that send data, change the method, carry credentials or headers, or
# read a config file. Any of these ends the exemption.
_SEND_FLAGS = {
    "-d", "--data", "--data-raw", "--data-binary", "--data-urlencode", "--data-ascii",
    "-f", "--form", "--form-string", "-t", "--upload-file", "-x", "--request",
    "-u", "--user", "-h", "--header", "-b", "--cookie", "-k", "--config", "-e", "--referer",
    "--json", "--post-data", "--post-file", "--method", "--body-data", "--body-file",
    "--password", "--http-user", "--http-password", "-i", "--input-file",
    "-method", "-body", "-infile", "-headers", "-credential", "-websession", "-form",
    "-usedefaultcredentials", "-token", "-authentication",
}
_OUTPUT_FLAGS = {"-o", "--output", "--output-document", "-p", "--directory-prefix",
                 "-outfile"}


def _flag_name(tok: str) -> str:
    name = tok.split("=", 1)[0]
    return name if name.startswith("--") else name.lower() if name.startswith("-") else ""


def _bad_output_path(value: str) -> bool:
    v = value.strip().strip("'\"").replace("\\", "/")
    return (v.startswith(("/", "~")) or ".." in v.split("/")
            or (len(v) > 1 and v[1] == ":"))


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
    if head not in _FETCH_CMDS:
        return False
    for i, tok in enumerate(tokens[1:], start=1):
        if tok.startswith("@"):
            return False
        name = _flag_name(tok)
        if not name:
            continue
        if name in _SEND_FLAGS or name.lower() in _SEND_FLAGS:
            return False
        if name.lower() in _OUTPUT_FLAGS:
            value = tok.split("=", 1)[1] if "=" in tok else (
                tokens[i + 1] if i + 1 < len(tokens) else "")
            if _bad_output_path(value):
                return False
    return True


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
