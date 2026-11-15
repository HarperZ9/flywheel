"""scrub_rules.py -- the shapes the secret scrubber recognises, in the order
it applies them.

Each rule is (code, pattern, group, check). `group` holds the secret (0 means
the whole match). `check` is None for a shape that is a secret by itself (a
provider key format, a private key block, a webhook URL) and a function for a
shape that is a secret only when its value looks like one: a value after a
credential-bearing name, a bearer, authorization or API-key header, a cookie,
a token in a URL, a URL's user part. A header value sits on the header's own
line, and a word, a number, a date or a path after a header name is not a
token. The name-based rules skip a placeholder, a call or attribute access,
a dotted name, or a word such as `true` or `string`, so code and prose that
mention a password are left alone; `scrub_shape.py` holds the value-shape
rules that decide the rest (a number, a date, a path or a short word is a
setting).

Provider prefixes carry short minimum lengths on purpose: a token cut short by
a line wrap or a length cap is still a secret, and the prefix alone carries
almost no false-positive risk.
"""
from __future__ import annotations

import re
from typing import Callable

from canon.workspace.scrub_shape import (
    cookie_is_secret,
    header_value_is_secret,
    name_class,
    shape_is_secret,
    userinfo_is_token,
)

REDACTED = "[REDACTED:{code}]"
MARKER_RE = re.compile(r"\[REDACTED:[a-z0-9-]+\]")
_SECRET_WORD = r"(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PASSPHRASE|PASS|PWD|CREDENTIALS?)"
# A placeholder is the WHOLE value, never a prefix of it, so a value such as
# `[REDACTED:aws-access-key]:<secret>` or `$2b$12$...` is not skipped.
_PLACEHOLDER = re.compile(
    r"^(?:<[^<>]*>|\$\{[A-Za-z_][A-Za-z0-9_]*(?::?[-=?+][^{}]*)?\}|(?-i:\$[A-Z_][A-Z0-9_]*)|"
    r"%[A-Za-z_][A-Za-z0-9_]*%|\{\{[^{}]*\}\}|\{[A-Za-z_][A-Za-z0-9_]*\}|x+|\*+|\.+|"
    r"changeme|your[_-][A-Za-z0-9_-]*|\[REDACTED:[a-z0-9-]+\])$", re.IGNORECASE)
_NOT_SECRET = frozenset({
    "true", "false", "none", "null", "nil", "yes", "no", "on", "off", "empty",
    "required", "optional", "undefined", "string", "str", "number", "int",
    "integer", "float", "bool", "boolean", "bytes", "object", "any", "unknown",
    "lambda", "enabled", "disabled",
})
_DOTTED = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
_NAME = re.compile(r"[A-Za-z0-9_.\-]+")
_SEGMENT_WORDS = ("key", "token", "secret", "password", "passwd", "pwd", "pass",
                  "passphrase", "credential", "credentials", "apikey", "auth")
# A cut token is still a secret; a lower-case word after the prefix (hf_transfer,
# npm_lifecycle_event) is a name, unless it is as long as a real token.
_RANDOM_TAIL = r"(?:[A-Za-z0-9]{30,}|(?=[A-Za-z0-9]*[A-Z0-9])[A-Za-z0-9]{8,})(?![A-Za-z0-9_])"
_VALUE = r"(\"[^\"\n]{4,}\"|'[^'\n]{4,}'|<[^<>\n]*>|[^\s\"'`,;(){}\[\]]{4,})"
# Every pattern runs in time linear in its input. A name is read whole
# (atomic or possessive) and a lookahead asks whether it holds a secret word,
# because a word between two optional runs of the same characters backtracks
# once per split of a long name. A match starts where a name starts, never
# inside a dotted or underscored run, and a URL scheme and a URL password
# have a length cap, so a long run of text is scanned once, not once per
# character.
#
# A `name=value` right after `?` or `&` is a URL query parameter, which has
# its own rule whose value ends at the next `&` or `#`; the assignment rules
# leave it alone. A name after `?` or `&` followed by `:` is still theirs. The
# group is atomic, so a later failure never retries the lookahead.
_NOT_A_QUERY = r"(?>(?<![?&])|(?=[A-Za-z0-9_.\-]*+\s*:))"
_NAME_START = r"(?<![A-Za-z0-9])(?<![A-Za-z0-9][_.\-])" + _NOT_A_QUERY
# An assignment name starts after a character that cannot be in a name, or
# after the `-` or `--` of a command-line flag (`--api-token=...`).
_FLAG_START = (r"(?>(?<![A-Za-z0-9_.\-])|(?<=-)(?<![^\s\"'=]-)|(?<=--)(?<![^\s\"'=]--))"
               + _NOT_A_QUERY)
_SCHEME = r"\b[a-zA-Z][a-zA-Z0-9+.\-]{0,255}://"


def _segment_name(words: tuple[str, ...]) -> str:
    """A captured name of `[_.-]`-joined segments, one of which is in `words`."""
    return (r"(?=(?:[a-z0-9]+[_.\-])*(?:" + "|".join(words) + r")(?![a-z0-9]))"
            r"((?>[a-z0-9]+(?:[_.\-][a-z0-9]+)*))")


def beyond_markers(value: str) -> str:
    """What is left of a value once earlier markers and the punctuation around
    them are removed; empty when the value is only an earlier redaction."""
    return MARKER_RE.sub("", value).strip(" .,;:!?\"'()[]{}<>")


def _prose_colon(match: re.Match[str], group: int) -> bool:
    """True for `word: short-word` inside a sentence ("Fix token: expire it"),
    which is prose. A config key is compound (`db_password:`) or starts its
    line (YAML), and a value with a digit, a symbol or twelve letters is kept
    as a secret either way."""
    head = match.string[match.start():match.start(group)]
    if "=" in head or ":" not in head or re.search(r"[_.\-]", head.split(":")[0]):
        return False
    # Only the last 256 characters before the name decide whether it starts
    # its line, so a long line with many names is not re-read once per name.
    window = match.string[max(0, match.start() - 256):match.start()]
    if not window.rsplit("\n", 1)[-1].strip(" \t-*#>"):
        return False
    value = match.group(group).strip("\"'")
    return value.isalpha() and len(value) < 12


def _name_before(match: re.Match[str], group: int) -> str:
    """The name the value is assigned to: the last name-shaped run of text
    between the start of the match and the value."""
    names = _NAME.findall(match.string[match.start():match.start(group)])
    return names[-1] if names else ""


def _value_check(match: re.Match[str], group: int, code_refs: bool) -> bool:
    raw = match.group(group)
    quoted = raw[:1] in "\"'" and raw[-1:] == raw[:1] and len(raw) > 1
    value = (raw[1:-1] if quoted else raw).strip()
    if _PLACEHOLDER.match(value) or _prose_colon(match, group):
        return False
    if MARKER_RE.search(value):
        return bool(beyond_markers(value))  # a marker plus more: the rest is secret
    if value.lower() in _NOT_SECRET:
        return False
    if code_refs and not quoted:
        after = match.string[match.end(group):match.end(group) + 1]
        if after in ("(", "[", ".") or _DOTTED.match(value):
            return False
    return shape_is_secret(value, name_class(_name_before(match, group)))


def value_is_secret(match: re.Match[str], group: int) -> bool:
    """A value after a credential-bearing name is a secret unless it is a
    placeholder, a code reference, an ordinary word, or a setting by its shape
    (`scrub_shape.shape_is_secret`)."""
    return _value_check(match, group, code_refs=True)


def data_value_is_secret(match: re.Match[str], group: int) -> bool:
    """The same check for a value that is data, never code: a JSON string or
    a URL query parameter."""
    return _value_check(match, group, code_refs=False)


def header_is_secret(match: re.Match[str], group: int) -> bool:
    """A bearer, authorization or API-key header value, unless it is a
    placeholder or a word that is never a secret (`required`), or its shape
    says it is not a token (`scrub_shape.header_value_is_secret`)."""
    value = match.group(group)
    if _PLACEHOLDER.match(value) or value.lower() in _NOT_SECRET:
        return False
    return header_value_is_secret(value)


def cookie_value_is_secret(match: re.Match[str], group: int) -> bool:
    return cookie_is_secret(match.group(group))


def userinfo_is_secret(match: re.Match[str], group: int) -> bool:
    """A URL user part with no password, unless it is a placeholder or a
    plain user name (`scrub_shape.userinfo_is_token`)."""
    value = match.group(group)
    return not _PLACEHOLDER.match(value) and userinfo_is_token(value)


def _p(pattern: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile(pattern, flags)


Check = Callable[[re.Match[str], int], bool] | None
RULES: tuple[tuple[str, re.Pattern[str], int, Check], ...] = (
    ("private-key", _p(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----"
        r"(?:.*?-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|.*\Z)", re.DOTALL), 0, None),
    ("private-key", _p(r"PuTTY-User-Key-File-\d+:.*?(?:Private-MAC:[^\n]*|\Z)", re.DOTALL), 0, None),
    ("anthropic-key", _p(r"\bsk-ant-[A-Za-z0-9_\-]{4,}"), 0, None),
    ("openai-key", _p(r"\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{4,}|\bsk-[A-Za-z0-9]{20,}"), 0, None),
    ("github-token", _p(r"\b(?:gh[pousr]_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,})"), 0, None),
    ("gitlab-token", _p(r"\bglpat-[A-Za-z0-9_\-]{8,}"), 0, None),
    ("slack-token", _p(r"\bx(?:ox[abposr]|app)-[A-Za-z0-9\-]{8,}"), 0, None),
    ("slack-webhook", _p(r"https://hooks\.slack\.com/services/\S+"), 0, None),
    ("discord-webhook", _p(r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\S+"), 0, None),
    ("aws-access-key", _p(r"\b(?:AKIA|ASIA)[0-9A-Z]{12,}"), 0, None),
    ("google-api-key", _p(r"\bAIza[0-9A-Za-z_\-]{20,}|\bGOCSPX-[A-Za-z0-9_\-]{8,}"
                          r"|\bya29\.[A-Za-z0-9_\-]{8,}"), 0, None),
    ("stripe-key", _p(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{8,}|\bwhsec_[A-Za-z0-9]{8,}"), 0, None),
    ("huggingface-token", _p(r"\bhf_" + _RANDOM_TAIL), 0, None),
    ("npm-token", _p(r"\bnpm_" + _RANDOM_TAIL), 0, None),
    ("pypi-token", _p(r"\bpypi-AgE[A-Za-z0-9_\-]{8,}"), 0, None),
    ("provider-token", _p(
        r"\bdo[por]_v1_[a-f0-9]{8,}|\bshp(?:at|ca|pa|ss)_[a-fA-F0-9]{8,}"
        r"|\bSG\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}|\bSK[0-9a-fA-F]{32}\b"
        r"|\b\d{8,10}:AA[A-Za-z0-9_\-]{30,}"), 0, None),
    ("jwt", _p(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), 0, None),
    ("bearer-header", _p(r"(?i)\bbearer[ \t]+([A-Za-z0-9._~+/\-]{8,}=*)"), 1, header_is_secret),
    ("auth-header", _p(r"(?i)\bauthorization[ \t]*:[ \t]*(?:basic|token|digest)[ \t]+"
                       r"([A-Za-z0-9._~+/=\-]{8,})"), 1, header_is_secret),
    ("cookie-header", _p(r"(?i)\b(?:set-)?cookie\s*:\s*([A-Za-z0-9_.\-]+=[^\s;\"']*"
                         r"(?:;\s*[A-Za-z0-9_.\-]+(?:=[^\s;\"']*)?)*)"), 1,
     cookie_value_is_secret),
    ("api-key-header", _p(r"(?i)\b(?:x-api-key|api-key|x-auth-token)[ \t]*[:=][ \t]*[\"']?"
                          r"([^\s\"',;]{8,})"), 1, header_is_secret),
    ("connection-string", _p(_SCHEME + r"[^\s:/@\"']*:(?!\d+(?:[/?#]|$))([^\s@\"']{1,512})@"),
     1, None),
    ("connection-string", _p(_SCHEME + r"([^\s:/@\"']+)@"), 1, userinfo_is_secret),
    ("url-credential", _p(
        r"(?i)[?&]" + _segment_name(_SEGMENT_WORDS + ("sig", "signature", "code")) +
        r"=([^&\s#\"']{4,})"), 2, data_value_is_secret),
    ("azure-key", _p(r"(?i)\b(?:AccountKey|SharedAccessSignature|SharedAccessKey)=([^;\s\"']{8,})"),
     1, None),
    ("npmrc-token", _p(r":_(?:authToken|auth|password)=([^\s\"']{8,})"), 1, None),
    ("json-secret", _p(
        r"(?i)\\?\"(?=[a-z0-9_\-]*(?:api[_-]?key|token|secret|password|passwd|credential))"
        r"[a-z0-9_\-]*+\\?\"\s*:\s*\\?\"([^\"\\\n]{4,})\\?\""), 1, data_value_is_secret),
    ("password-field", _p(
        r"(?i)" + _NAME_START + r"(?:[a-z0-9]+[_.\-])*(?:password|passwd|pwd|pass|passphrase)"
        r"\s*[:=]\s*" + _VALUE), 1, value_is_secret),
    ("env-assignment", _p(
        _NOT_A_QUERY + r"\b(?=[A-Z0-9_]*" + _SECRET_WORD + r")[A-Z][A-Z0-9_]*+\s*[=:]\s*"
        r"(\"[^\"\n]{4,}\"|'[^'\n]{4,}'|<[^<>\n]*>|[^\s\"']{4,})"), 1, value_is_secret),
    ("env-assignment", _p(
        r"(?i)" + _FLAG_START + r"(?<!\$\{)" + _segment_name(_SEGMENT_WORDS) +
        r"\s*[=:]\s*" + _VALUE), 2, value_is_secret),
)
