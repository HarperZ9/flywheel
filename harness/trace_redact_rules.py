"""The redaction catalog (7.7): one versioned rule list for every Flywheel
redaction path, credential rules first, then personal-data rules.

Every pattern is written to run in time linear in its input: a lookbehind at
the start keeps the engine from retrying inside a run of the rule's own
characters, quantifiers are bounded, and possessive forms stop backtracking
where giving characters back could never produce a match. Multi-line blocks
(PEM, PuTTY) are found by a line-based finder instead of one expression.

A rule marked `lower` runs on an ASCII-lowercased copy of the text, whose
offsets match the original, with patterns written in lowercase. The engine
fast-searches a literal prefix, which a case-insensitive alternation defeats:
on plain prose the case-insensitive keyword alternation measured 55 ms per
MiB and one literal pattern per keyword 8 ms. Validators always read the
original text, since base64 values are case-sensitive.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Iterator

from .trace_redact_finders import (basic_value, bearer_value, cookie_value, iban_valid,
                                   ipv6_valid, jwt_header_valid, luhn_valid, oauth_codes,
                                   pem_blocks, putty_blocks, userinfo_value)

CATALOG_VERSION = "trace-redact/2026-09-26.2"


@dataclass(frozen=True)
class Rule:
    id: str
    cls: str
    kind: str
    pattern: re.Pattern | tuple[re.Pattern, ...] | None
    group: tuple[int, ...] = (0,)
    validator: Callable[[str], bool] | None = None
    finder: Callable[[str], Iterator[tuple[int, int]]] | None = None
    default: bool = True
    tail: re.Pattern | None = None
    note: str = ""
    lower: bool = False

    @property
    def patterns(self) -> tuple[re.Pattern, ...]:
        if self.pattern is None:
            return ()
        return self.pattern if isinstance(self.pattern, tuple) else (self.pattern,)


_c = re.compile
_TOK = r"(?<![A-Za-z0-9_\-])"
_SEPARATED = ("api_key", "access_key", "private_key", "client_secret", "auth_token")
_KEYWORDS = ("password", "passwd", "pwd", "secret", "token", "credential") + tuple(
    k.replace("_", sep) for k in _SEPARATED for sep in ("_", "-", ""))
_VALUE = (r"s?[\"']?[ \t]{0,8}+[:=][ \t]{0,8}+(?:\"([^\"\r\n]{8,512}+)\"|"
          r"'([^'\r\n]{8,512}+)'|([^\s\"',;&]{8,512}+))")
ASSIGNMENTS = tuple(_c(re.escape(k) + _VALUE) for k in _KEYWORDS)


def _credential(rule_id, pattern, note, *, tail=None, group=(0,), validator=None,
                finder=None, kind="secret", lower=False):
    return Rule(rule_id, "credential", kind, pattern, group, validator, finder, True,
                tail, note, lower)


def _personal(rule_id, pattern, note, *, validator=None, default=True):
    return Rule(rule_id, "personal", rule_id, pattern, (0,), validator, None, default,
                None, note)


CREDENTIAL_RULES = (
    _credential("pem_private_key", None, "any PEM private-key block; an unterminated "
                "block is redacted to the end of the text", finder=pem_blocks, kind="key"),
    _credential("aws_access_key_id", _c(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}"
                r"(?![A-Za-z0-9])"), "a 20-character id starting AKIA or ASIA",
                tail=_c(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{4,15}\Z")),
    _credential("aws_secret_assignment", _c(r"aws_secret_access_key[\"']?[ \t]{0,8}+[:=]"
                r"[ \t]{0,8}+[\"']?([a-z0-9/+=]{40})(?![a-z0-9/+=])"),
                "the value assigned to aws_secret_access_key", group=(1,), lower=True),
    _credential("github_token", _c(_TOK + r"(?:gh[pousr]_[A-Za-z0-9]{30,255}+|"
                r"github_pat_[A-Za-z0-9_]{22,255}+)"), "GitHub token prefixes",
                tail=_c(_TOK + r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{4,254}\Z")),
    _credential("sk_api_key", _c(_TOK + r"sk-(?:(?:live|proj|ant)-?[A-Za-z0-9_\-]{10,255}+"
                r"|[A-Za-z0-9_\-]{20,255}+)"), "sk- keys (OpenAI, Anthropic); a hyphenated "
                "name that starts sk- and runs 20 or more characters also matches",
                tail=_c(_TOK + r"sk-(?:proj-|ant-)?[A-Za-z0-9_\-]{4,254}\Z")),
    _credential("slack_token", _c(r"(?<![A-Za-z0-9])xox[abeprs]-[A-Za-z0-9\-]{10,255}+"),
                "Slack xox tokens",
                tail=_c(r"(?<![A-Za-z0-9])xox[abeprs]-[A-Za-z0-9\-]{4,254}\Z")),
    _credential("stripe_key", _c(r"(?<![A-Za-z0-9_])(?:sk|rk)_live_[A-Za-z0-9]{10,255}+"),
                "Stripe live secret and restricted keys",
                tail=_c(r"(?<![A-Za-z0-9_])(?:sk|rk)_live_[A-Za-z0-9]{4,254}\Z")),
    _credential("google_api_key", _c(_TOK + r"AIza[0-9A-Za-z_\-]{35}(?![0-9A-Za-z_\-])"),
                "Google API keys", tail=_c(_TOK + r"AIza[0-9A-Za-z_\-]{4,34}\Z")),
    _credential("jwt", _c(_TOK + r"eyJ[A-Za-z0-9_\-]{12,4096}+\.eyJ[A-Za-z0-9_\-]"
                r"{8,4096}+\.[A-Za-z0-9_\-]{16,4096}+"), "a JWT whose header decodes to "
                "JSON with alg; a token with an empty or short signature is not matched",
                validator=jwt_header_valid,
                tail=_c(_TOK + r"eyJ[A-Za-z0-9_\-]{12,4096}+\.eyJ[A-Za-z0-9_.\-]{0,8192}\Z")),
    _credential("bearer_token", _c(r"(?<![a-z0-9_\-])bearer[ \t]{1,8}+"
                r"([a-z0-9._~+/=\-]{16,4096}+)"), "a bearer value of 16 or more characters "
                "holding a digit or a symbol", group=(1,), validator=bearer_value, lower=True),
    _credential("basic_auth", _c(r"(?<![a-z0-9_\-])basic[ \t]{1,8}+([a-z0-9+/]{6,4096}+"
                r"={0,2}+)"), "a Basic value that decodes to user:password", group=(1,),
                validator=basic_value, lower=True),
    _credential("url_userinfo", _c(r"://([^/\s@:]{1,256}+(?::[^/\s@]{0,256}+)?)@"),
                "userinfo with a password, or a user part of 16 or more characters",
                group=(1,), validator=userinfo_value),
    _credential("credential_assignment", ASSIGNMENTS, "a value of 8 or more characters "
                "assigned to a credential-named key; example code such as token = "
                "get_token(user) also matches, and so does PWD=/path", group=(1, 2, 3),
                lower=True),
    _credential("azure_key_assignment", _c(r"(?<![a-z0-9])(?:accountkey|sharedaccesskey)"
                r"[ \t]{0,4}+=[ \t]{0,4}+([a-z0-9+/]{20,256}+={0,2}+)"),
                "Azure AccountKey= and SharedAccessKey= values", group=(1,), lower=True),
    _credential("npm_token", _c(r"(?<![A-Za-z0-9_])npm_[A-Za-z0-9]{36}(?![A-Za-z0-9])"),
                "npm access tokens", tail=_c(r"(?<![A-Za-z0-9_])npm_[A-Za-z0-9]{4,35}\Z")),
    _credential("pypi_token", _c(_TOK + r"pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{50,1000}+"),
                "PyPI API tokens",
                tail=_c(_TOK + r"pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{0,1000}\Z")),
    _credential("hf_token", _c(r"(?<![A-Za-z0-9_])hf_[A-Za-z0-9]{30,64}+(?![A-Za-z0-9])"),
                "Hugging Face tokens", tail=_c(r"(?<![A-Za-z0-9_])hf_[A-Za-z0-9]{8,29}\Z")),
    _credential("cookie_header", _c(r"(?<![a-z0-9\-])(?:set-)?cookie[ \t]{0,4}+:[ \t]{0,4}+"
                r"([^\r\n\"']{1,8192}+)"), "Cookie and Set-Cookie values that hold "
                "name=value; prose such as 'cookie: a=b' also matches", group=(1,),
                validator=cookie_value, lower=True),
    _credential("url_signature_param", _c(r"[?&](?:sig|x-amz-signature|x-amz-credential|"
                r"x-goog-signature|access_token)=([^&#\s\"'<>]{1,4096}+)"),
                "signature and access-token query parameters", group=(1,), lower=True),
    _credential("oauth_code_param", None, "a code parameter only in a URL that also "
                "carries state or whose path names oauth, callback or authorize",
                finder=oauth_codes),
    _credential("docker_auth", _c(r"\"auth\"[ \t]{0,4}+:[ \t]{0,4}+\"([A-Za-z0-9+/]"
                r"{8,4096}+={0,2}+)\""), "Docker config auth values", group=(1,)),
    _credential("kubeconfig_secret", _c(r"(?m)^[ \t]{0,32}+(?:client-key-data|token)"
                r"[ \t]{0,4}+:[ \t]{0,4}+([a-z0-9+/=._\-]{16,8000}+)"),
                "kubeconfig client-key-data and token values", group=(1,), lower=True),
    _credential("age_secret_key", _c(r"(?<![A-Za-z0-9])AGE-SECRET-KEY-1[0-9A-Z]{58}"
                r"(?![0-9A-Z])"), "age secret keys",
                tail=_c(r"(?<![A-Za-z0-9])AGE-SECRET-KEY-1[0-9A-Z]{0,57}\Z")),
    _credential("putty_key", None, "a PuTTY key file body from its first line through "
                "Private-MAC", finder=putty_blocks, kind="key"),
)

PERSONAL_RULES = (
    _personal("email", _c(r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]{1,64}+@(?:[A-Za-z0-9\-]"
              r"{1,63}+\.){1,8}[A-Za-z]{2,24}+(?![A-Za-z0-9\-])"), "a git or ssh remote "
              "such as git@github.com also matches"),
    _personal("phone", _c(r"(?<![\d+(])(?:\+[1-9]\d{7,14}+(?!\d)|(?:\+?1[ .\-]?+)?(?:\("
              r"[2-9]\d{2}\)|[2-9]\d{2})[ .\-]?+[2-9]\d{2}[ .\-]?+\d{4}(?!\d))"),
              "E.164 and North American numbers; ten-digit ids and timestamps also match"),
    _personal("card_number", _c(r"(?<![\d])\d{4}(?:[ \-](?:\d{4}[ \-]\d{4}[ \-]\d{1,7}|"
              r"\d{6}[ \-]\d{5})|\d{9,15})(?![\d])"), "13 to 19 digits that pass Luhn; "
              "one random long number in ten passes Luhn", validator=luhn_valid),
    _personal("us_ssn", _c(r"(?<![\d\-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}"
              r"(?![\d\-])"), "US Social Security numbers in valid ranges"),
    _personal("iban", _c(r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]"
              r"{1,3})?(?![A-Za-z0-9])"), "IBANs of their country's length that pass "
              "mod 97", validator=iban_valid),
    _personal("ipv4", _c(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|"
              r"2[0-4]\d|1\d\d|[1-9]?\d)(?!\.?\d)"), "off by default; version strings "
              "such as 1.2.3.4 match", default=False),
    _personal("ipv6", _c(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{0,4}+:){2,7}[0-9A-Fa-f]{0,4}+"
              r"(?![0-9A-Fa-f:])"), "off by default; addresses with at least three hex "
              "digits", validator=ipv6_valid, default=False),
    _personal("lat_long", _c(r"(?<![\d.\-])-?(?:90(?:\.0{3,10}+)?|[1-8]?\d\.\d{3,10}+)[ \t]"
              r"{0,4}+,[ \t]{0,4}+-?(?:180(?:\.0{3,10}+)?|(?:1[0-7]\d|[1-9]?\d)\.\d{3,10}+)"
              r"(?![\d.])"), "off by default; decimal coordinate pairs", default=False),
)

RULES = CREDENTIAL_RULES + PERSONAL_RULES
INDEX = {rule.id: n for n, rule in enumerate(RULES)}

# Each documented miss has a fixture in tests/test_trace_redact_misses.py and
# a row in docs/trace-redaction.md; the test holds the three lists equal.
DOCUMENTED_MISSES = (
    ("password_without_named_key", "a password written in prose, with no credential-named key"),
    ("secret_split_across_lines", "a secret split across lines, tool calls or messages"),
    ("encoded_secret", "a secret encoded as base64 or hex (Docker auth values aside)"),
    ("custom_token_format", "a token format the catalog does not name"),
    ("bare_azure_key", "an Azure key with no prefix and no assignment name"),
    ("secret_in_binary_content", "a secret inside an image, a PDF or compressed binary"),
    ("personal_free_text", "names, street addresses, dates of birth and health facts"),
    ("national_id_other_than_ssn_or_iban", "national identifiers other than US SSN and IBAN"),
    ("unicode_lookalike", "a token written with look-alike Unicode letters"),
    ("json_nested_deeper_than_four_levels", "JSON nested more than four levels deep inside "
     "strings, where only the key name would reveal the secret"),
)


def credential_rules() -> tuple[Rule, ...]:
    return CREDENTIAL_RULES


def enabled(*, personal: bool = False, enable=()) -> tuple[Rule, ...]:
    """Credential rules always; personal rules on request; default-off rules
    only when named in `enable`."""
    named = set(enable)
    return tuple(r for r in RULES if r.cls == "credential" or (
        personal and (r.default or r.id in named)))
