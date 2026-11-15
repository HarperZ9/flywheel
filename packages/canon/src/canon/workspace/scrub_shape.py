"""scrub_shape.py -- whether a value after a credential-bearing name is a secret.

The name-based rules match a name that carries a credential word (`password`,
`token`, `secret`, `key` and the rest) followed by `=` or `:` and a value. The
name says what the value is for. The value's shape says whether it is one:

- A number (at most 19 digits), a date or a time, a path, an AWS resource
  name (`arn:...`), or a boolean or null word is a setting after any name:
  `KEY_COUNT=1000`, `pass_rate=0.95`, `second pass: 2026-10-01`,
  `private_key_path: ~/.ssh/id_ed25519`. A path starts at `/`, `~/`, `./`,
  `../`, a drive letter or a variable, and no segment of it holds a random
  run (below) or is sixteen or more base64 characters mixing both cases.
  After a name that holds a password or a token, a path also needs two
  segments (`/hunter2` is a password) and must not be base64-shaped (only
  letters, digits, `+`, `/` and `=`, with upper case, lower case and a
  digit), so a base64 key that starts with `/` is not read as a path.
- A name holds a password when its last secret word is a password word and
  every word after it names which password (`DB_PASSWORD`, `smtp_pass`,
  `DB_PASSWORD_PROD`, `ADMIN_PASSWORD_2`, `password_confirmation`). Any
  value that is not a setting is a secret there. A person picks a password,
  and a word is a password.
- A name holds a token when it ends in another credential word
  (`GITHUB_TOKEN`, `client_secret`, `AWS_CREDENTIALS`) or in `key` after a
  credential word (`api_key`, `SECRET_KEY`). A short word of up to ten
  letters is a setting there (`token: bearer`), since an issued key or token
  never reads as one. Anything else is a secret.
- Any other matching name describes a secret: a word such as `type`, `path`,
  `min` or `policy` follows a password word (`PASSWORD_MIN_LENGTH`), any word
  follows another credential word (`token_type`, `GITHUB_TOKEN_CI`), or the
  name has no secret word of its own (`KEY_PREFIX`, a bare `key` or `auth`,
  `MONKEY`). The value is a secret there only when it looks random: twelve
  or more characters with no space that hold a random run, or that mix both
  cases with `+`, `/` or `=`. A random run is a run of eight or more letters
  and digits that is not a word followed by a number and not a number
  followed by up to two letters (`a8f3k2j9x7m1`, a hex digest). An
  identifier with a version, date or region digit (`kv-prod-eastus2`,
  `feature_flag_v2`) has none.

A number is a setting after a password word too, so a numeric PIN after
`password=` passes through: a declared limit.
"""
from __future__ import annotations

import re
from urllib.parse import unquote

PASSWORD = "password"
CREDENTIAL = "credential"
QUALIFIED = "qualified"

_PASSWORD_WORDS = frozenset({"password", "passwords", "passwd", "pwd", "pass", "passphrase"})
_PASSWORD_ENDINGS = ("password", "passwords", "passwd", "passphrase")
_CREDENTIAL_WORDS = frozenset({"token", "tokens", "secret", "secrets", "credential",
                               "credentials", "apikey", "apikeys"})
_KEY_WORDS = frozenset({"key", "keys"})
_KEY_CONTEXT = frozenset({"api", "access", "private", "client", "signing", "master",
                          "encryption", "account", "service", "auth"})
# A word after a password word that describes the password rather than
# naming which one it is. `DB_PASSWORD_PROD` holds a password;
# `PASSWORD_POLICY` and `password_min_length` describe one.
_DESCRIPTORS = frozenset({
    "type", "types", "kind", "format", "mode", "method", "scheme", "algorithm", "alg",
    "policy", "rule", "rules", "pattern", "regex", "strength", "version", "scope", "scopes",
    "prefix", "suffix", "name", "names", "id", "ids", "arn", "label", "hint", "ref",
    "path", "paths", "file", "files", "filename", "dir", "directory", "location",
    "url", "uri", "endpoint", "host", "header", "field", "param", "var", "env", "source",
    "ttl", "expiry", "expires", "expiration", "lifetime", "age", "timeout", "interval",
    "rotation", "count", "len", "length", "size", "min", "max", "limit", "index",
    "rate", "threshold", "through", "fail", "status", "result", "output", "input",
    "prompt", "message", "help", "description", "error",
    "helper", "manager", "store", "storage", "backend", "provider",
})
_NUMBER = re.compile(r"[+-]?(?:\d+(?:[_,]\d+)*)?(?:\.\d+)?(?:[eE][+-]?\d+)?")
_DATE = re.compile(r"\d{4}[-/]\d{2}[-/]\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
                   r"(?:Z|[+-]\d{2}:?\d{2})?)?|\d{1,2}:\d{2}(?::\d{2})?")
_PATH = re.compile(r"(?:~|\.{1,2}|[A-Za-z]:|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|%[A-Za-z_]\w*%)?"
                   r"[\\/](?:[\w.\-~@+]+[\\/])*[\w.\-~@+]*")
_BASE64 = re.compile(r"[A-Za-z0-9+/=]+")
_ARN = re.compile(r"arn:[a-z0-9-]+:[a-z0-9-]+:[a-z0-9-]*:\d*:\S+")
_WORD = re.compile(r"[A-Za-z][a-z]{0,9}")
_PROSE_WORD = re.compile(r"[A-Za-z][a-z]{0,18}")
_URL = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://")
_RUN = re.compile(r"[A-Za-z0-9]+")
# A word, a number, or a word followed by a number (`eastus2`, `v2`, `2024`,
# `GitHubUser42`), or a number followed by up to two letters (`64k`, `1st`).
_PLAIN_RUN = re.compile(r"[A-Za-z]*\d*|\d+[A-Za-z]{1,2}")
_BOOLEAN_WORDS = frozenset({"true", "false", "yes", "no", "on", "off", "none", "null", "nil"})


def name_segments(name: str) -> list[str]:
    """The lower-case words of a name: `apiKey`, `API_KEY` and `api-key` all
    give `api`, `key`."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return [s for s in re.split(r"[_.\-\s]+", spaced.lower()) if s]


def _secret_word(segment: str, before: list[str]) -> str | None:
    """PASSWORD or CREDENTIAL when `segment` is a secret word in its name."""
    if segment in _PASSWORD_WORDS or segment.endswith(_PASSWORD_ENDINGS):
        return PASSWORD
    if segment in _CREDENTIAL_WORDS or segment.endswith(tuple(_CREDENTIAL_WORDS)):
        return CREDENTIAL
    if segment in _KEY_WORDS and any(s in _KEY_CONTEXT or s in _CREDENTIAL_WORDS
                                     or s in _PASSWORD_WORDS for s in before):
        return CREDENTIAL
    return None


def name_class(name: str) -> str:
    """The class of the last secret word in the name. A name that ends in it
    is PASSWORD or CREDENTIAL. After a password word, words that only say
    which password it is keep the name PASSWORD (`DB_PASSWORD_PROD`,
    `ADMIN_PASSWORD_2`, `password_confirmation`), and a word that describes
    it makes the name QUALIFIED (`PASSWORD_MIN_LENGTH`, `password_policy`).
    After another secret word any following word makes the name QUALIFIED
    (`token_type`, `private_key_path`, `GITHUB_TOKEN_CI`), since an issued
    token under such a name still looks random. A name with no secret word
    (`KEY_COUNT`, a bare `key` or `auth`, `monkey`) is QUALIFIED."""
    segments = name_segments(name) or [""]
    for i in range(len(segments) - 1, -1, -1):
        kind = _secret_word(segments[i], segments[:i])
        if kind is None:
            continue
        tail = segments[i + 1:]
        if not tail or (kind == PASSWORD and not _DESCRIPTORS.intersection(tail)):
            return kind
        return QUALIFIED
    return QUALIFIED


def _random_segment(segment: str) -> bool:
    """A path segment that holds a random run, or that is sixteen or more
    base64 characters mixing both cases (a digit-free stretch of a key)."""
    if random_run(segment):
        return True
    return bool(len(segment) >= 16 and _BASE64.fullmatch(segment)
                and re.search(r"[a-z]", segment) and re.search(r"[A-Z]", segment))


def _base64_shaped(value: str) -> bool:
    """Only base64 characters, with upper case, lower case and a digit."""
    return bool(_BASE64.fullmatch(value) and re.search(r"[a-z]", value)
                and re.search(r"[A-Z]", value) and re.search(r"\d", value))


def is_path(value: str, strict: bool = False) -> bool:
    """A path starts at `/`, `~/`, `./`, `../`, a drive letter or a variable,
    and no segment of it is random (`_random_segment`). `strict` (after a name that holds
    a secret) also needs two segments, so `/hunter2` is not a path, and a value
    that is base64-shaped is not a path either."""
    if not _PATH.fullmatch(value):
        return False
    segments = [s for s in re.split(r"[\\/]", value) if s]
    if any(_random_segment(s) for s in segments):
        return False
    return not strict or (len(segments) >= 2 and not _base64_shaped(value))


def ordinary(value: str, strict: bool = False) -> bool:
    """A number, a date or time, a path, an AWS resource name, or a boolean or
    null word. `strict` is passed to `is_path`."""
    if value.lower() in _BOOLEAN_WORDS or _DATE.fullmatch(value) or is_path(value, strict):
        return True
    if _ARN.fullmatch(value):
        return True
    digits = sum(c.isdigit() for c in value)
    return 0 < digits <= 19 and _NUMBER.fullmatch(value) is not None


def random_run(value: str) -> bool:
    """True when a run of eight or more letters and digits in `value` is not
    a word followed by a number: digits sit between letters (`a8f3k2j9`,
    `canaryV4lue`, a hex digest) or before more than two letters (`550e8400`).
    `kv-prod-eastus2`, `GitHubUser42` and `release-2026-10` have no such run."""
    return any(len(run) >= 8 and not _PLAIN_RUN.fullmatch(run) for run in _RUN.findall(value))


def looks_random(value: str) -> bool:
    """Twelve or more characters with no space, not a URL or an ordinary
    value, that hold a random run (`random_run`), or mix both cases with `+`,
    `/` or `=`."""
    if len(value) < 12 or re.search(r"\s", value) or _URL.match(value) or ordinary(value):
        return False
    if random_run(value):
        return True
    return bool(re.search(r"[a-z]", value) and re.search(r"[A-Z]", value)
                and re.search(r"[+/=]", value))


def shape_is_secret(value: str, kind: str) -> bool:
    """Whether `value`, after a name of class `kind`, is a secret."""
    if ordinary(value, strict=kind != QUALIFIED):
        return False
    if kind == PASSWORD:
        return True
    if kind == CREDENTIAL:
        return _WORD.fullmatch(value) is None
    return looks_random(value)


def userinfo_is_token(value: str) -> bool:
    """A URL user part with no password is a token when, with its percent
    escapes decoded, it holds a random run (`random_run`). A name such as
    `git`, `first.last`, `deploy-bot-2024`, `GitHubUser42` or an email address
    is not."""
    return random_run(unquote(value))


def header_value_is_secret(value: str) -> bool:
    """A header value (after `Bearer`, `Authorization: Basic`, `X-API-Key:`)
    is a token unless it is a setting (a number, a date, a path) or a
    lower-case or capitalised word of fewer than twenty letters, which reads
    as prose (`bearer authentication`, `Token placeholder`)."""
    return not (ordinary(value, strict=True) or _PROSE_WORD.fullmatch(value))


def cookie_is_secret(pairs: str) -> bool:
    """A cookie header is a secret when one of its values is: a value that
    looks random, or a secret-shaped value under a credential name. A consent
    or theme cookie is not."""
    for pair in pairs.split(";"):
        name, _, value = pair.strip().partition("=")
        value = value.strip().strip("\"")
        if not value or value.startswith("[REDACTED:"):
            continue
        kind = name_class(name)
        if looks_random(value) or (kind != QUALIFIED and shape_is_secret(value, kind)):
            return True
    return False
