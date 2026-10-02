"""rowan_handoff_redact.py -- the credential patterns a handoff brief applies.

Each pattern starts only at a fixed token, a word start, or a line that runs
the command it belongs to, and scans a bounded or single run from there, so
redaction time grows with the text and not with its square. A flag such as
`-p` names a password for a few commands and a port or a path for most, so it
is read only on a line that runs one of those commands first.

This is a pattern list. A credential in a shape it does not name passes,
which is why the brief lists REDACTION_IS_PATTERN_BASED in what it does not
prove. Standard library and engine scanners only.
"""
from __future__ import annotations

import re

from .bundle import scan_for_secrets
from .continuation_context import _BEARER, _CREDENTIAL_ASSIGNMENT, scrub_credentials

OMITTED = "[credential omitted]"
# A value that is already the marker is skipped, so running the patterns
# twice changes nothing. leaks() depends on that to re-run them.
_FRESH = r"(?!\[credential omitted\])"
_VALUE = _FRESH + r"('[^'\n]*'|\"[^\"\n]*\"|\S+)"
_URL_USERINFO = re.compile(r"(://)[^\s/@:]+:[^\s/@]+@")
# --password, --http-password, --passphrase, --pass. --no-password and
# --password-stdin take no value.
_LONG_FLAG = re.compile(r"(?i)(?<![\w-])(--(?!no-)(?:[a-z]+-){0,3}pass(?:word|wd|phrase)?)"
                        r"(=|[ \t]+(?!-))" + _VALUE)
# keytool -storepass and -keypass, OpenSSL -passin, -passout and -pass.
_WORD_FLAG = re.compile(r"(?<![\w-])(-(?:store|key|srcstore|srckey|deststore|destkey)?"
                        r"pass(?:word|in|out)?)([ \t]+)(?!-)" + _VALUE)
# curl -u name:secret, --user, -U, --proxy-user: the part after the colon.
# smbclient and the other Samba tools take -U name%secret, and DOMAIN\name.
_USER_FLAG = re.compile(r"(?<![\w-])(-[uU]|--(?:proxy-)?user)(=|[ \t]*)(['\"])?"
                        r"(\w[\w.@+\\-]*)([:%])" + _FRESH + r"((?(3)[^'\"\n]+|[^\s'\"]+))")
# Authorization: Basic, Token, Negotiate or NTLM, as a header or in git's
# http.extraheader. A bearer token is left to the engine's scrubber.
_AUTH_SCHEME = re.compile(r"(?i)\b((?:proxy-)?authorization['\"]?[ \t]*[:=][ \t]*"
                          r"(?:basic|token|negotiate|ntlm)[ \t]+)" + _FRESH + r"([\w+/=.~-]+)")
# DB_PASS=, MYSQL_PWD=, PGPASSWORD=, REDISCLI_AUTH=: a variable named for a
# password, set.
_SECRET_NAME = re.compile(
    r"(?i)(?<![\w.-])((?:[a-z][a-z0-9]{0,31}_){1,4}(?:pass|pwd|auth)"
    r"|(?:[a-z][a-z0-9_]{0,63}?)?pass(?:word|wd|phrase))(['\"]?[ \t]*[:=][ \t]*)" + _VALUE)
_NOT_SECRET = {"true", "false", "none", "null", "yes", "no", "on", "off", "''", '""'}
_LINKING = r"(?:is|was|are|were|now|still|set to|reset to|changed to|becomes|remains)"
# A keyword, up to two linking words, then a value that looks like a
# credential: quoted, or 8 or more characters with a digit or a symbol, so
# "token limit" and "the password is required" survive. "for admin" or "of
# the account" may sit between the keyword and a linking word.
_KEYWORD_VALUE = re.compile(
    r"(?i)\b(\w*(?:password|passwd|passphrase|secret(?:_access_key)?|api[ _-]?key"
    r"|access[ _-]?key|token))((?:[ \t]+(?:for|of)(?:[ \t]+[\w.@-]+){1,3}(?=[ \t]+"
    + _LINKING + r"\b))?(?:[ \t]+" + _LINKING + r"){0,2}\s+)" + _FRESH
    + r"('[^'\n]+'|\"[^\"\n]+\"|(?=\S*[\d/+=!@#$%^&*])\S{8,})")
# htpasswd -b takes the password as its last argument, before any closing
# quote or bracket a JSON form adds.
_HTPASSWD = re.compile(r"(?i)(?<![\w-])htpasswd(?![\w-])([^\n;&|]*)")
_BATCH_FLAG = re.compile(r"(?<![\w-])-[A-Za-z]*b[A-Za-z]*(?![\w-])")
_LAST_ARG = re.compile(r"(?<=[ \t])(?<!\[credential )(?!-)" + _FRESH
                       + r"('[^'\n]*'|\"[^\"\n]*\"|[^\s'\"]+)(?=[\"'}\]),]*[ \t]*$)")
# A secret fed to --password-stdin: a here-string, or echo piped into it.
_STDIN_FLAG = re.compile(r"(?i)(?<![\w-])--password-stdin(?![\w-])")
_HERE_STRING = re.compile(r"(<<<)([ \t]*)" + _VALUE)
_ECHO_PIPE = re.compile(r"(?<![\w-])(echo(?:[ \t]+-[neE]+)*)([ \t]+)" + _VALUE
                        + r"(?=[ \t]*\|)")
# Token shapes the engine's bundle scanner does not list.
_TOKEN_SHAPE = re.compile(r"\b(?:dckr_pat_[\w-]{20,}|glpat-[\w-]{20,}|github_pat_\w{40,}"
                          r"|npm_[A-Za-z0-9]{36}|hf_[A-Za-z0-9]{30,}|pypi-[\w-]{40,})")


def _command(pattern: str):
    return re.compile(r"(?i)(?<![\w-])(?:" + pattern + r")(?![\w-])")


# (the command, its password flag). mysql -p takes a glued value only, since
# `-p name` prompts and names a database.
_COMMAND_FLAGS = tuple((_command(command), re.compile(r"(?<![\w-])" + flag + _VALUE)) for
                       command, flag in (
    (r"(?:mysql|mariadb)[\w-]*", r"(-p)()(?=[^\s-])"),
    (r"sshpass", r"(-p)([ \t]*)(?!-)"),
    (r"(?:docker|podman|nerdctl|buildah|skopeo|oras|helm[ \t]+registry)[ \t]+login",
     r"(-p)([ \t]*)(?!-)"),
    (r"redis-cli", r"(-a)([ \t]+)(?!-)"),
    (r"mongo(?:sh|dump|restore|export|import|stat|top|files)?", r"(-p)([ \t]+)(?!-)"),
    (r"sqlcmd|bcp", r"(-P)([ \t]*)(?!-)"),
    (r"ldap(?:search|add|modify|delete|compare|passwd|whoami|modrdn|exop)",
     r"(-w)([ \t]+)(?!-)"),
))


def _keep(m: re.Match) -> str:
    return m.group(1) + m.group(2) + OMITTED


def _user_secret(m: re.Match) -> str:
    """uid:gid, as in `docker run -u 1000:1000`, is not a credential."""
    if m.group(4).isdigit() and m.group(6).isdigit():
        return m.group(0)
    return m.group(1) + m.group(2) + (m.group(3) or "") + m.group(4) + m.group(5) + OMITTED


def _htpasswd(m: re.Match) -> str:
    """htpasswd in batch mode: its last argument is the password."""
    if not _BATCH_FLAG.search(m.group(1)):
        return m.group(0)
    return m.group(0)[:m.start(1) - m.start(0)] + _LAST_ARG.sub(OMITTED, m.group(1), count=1)


def _unless_variable(m: re.Match) -> str:
    """`$TOKEN` names a secret without holding it, so it stays."""
    return m.group(0) if m.group(3).strip("'\"").startswith("$") else _keep(m)


def _stdin_secret(text: str) -> str:
    """Each line that runs --password-stdin: what it feeds to the flag."""
    out = []
    for line in text.split("\n"):
        if _STDIN_FLAG.search(line):
            line = _ECHO_PIPE.sub(_unless_variable, _HERE_STRING.sub(_unless_variable, line))
        out.append(line)
    return "\n".join(out)


def _named_secret(m: re.Match) -> str:
    value = m.group(3)
    if value.isdigit() or value.lower() in _NOT_SECRET:
        return m.group(0)
    return _keep(m)


def _command_flags(text: str) -> str:
    """Each line: a command's password flag, after the command that owns it."""
    out = []
    for line in text.split("\n"):
        for command, flag in _COMMAND_FLAGS:
            found = command.search(line)
            if found:
                line = line[:found.end()] + flag.sub(_keep, line[found.end():])
        out.append(line)
    return "\n".join(out)


def _own(text: str) -> str:
    """The patterns this module adds to the engine's scrubber."""
    value = _URL_USERINFO.sub(lambda m: m.group(1) + OMITTED + "@", text)
    value = _TOKEN_SHAPE.sub(OMITTED, value)
    value = _AUTH_SCHEME.sub(lambda m: m.group(1) + OMITTED, value)
    value = _LONG_FLAG.sub(_keep, value)
    value = _WORD_FLAG.sub(_keep, value)
    value = _USER_FLAG.sub(_user_secret, value)
    value = _command_flags(value)
    value = _HTPASSWD.sub(_htpasswd, value)
    value = _stdin_secret(value)
    value = _SECRET_NAME.sub(_named_secret, value)
    return _KEYWORD_VALUE.sub(_keep, value)


def redact(text) -> str:
    """Replace every credential shape named above with a marker."""
    return _own(scrub_credentials(str(text or "")))


def leaks(line: str) -> bool:
    """A rendered line that still carries a credential shape."""
    if scan_for_secrets(line) or _own(line) != line:
        return True
    return any("[credential" not in m.group(0)
               for pattern in (_CREDENTIAL_ASSIGNMENT, _BEARER) for m in pattern.finditer(line))
