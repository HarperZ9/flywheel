"""textutil.py -- shared text helpers used by every M4 seam.

Two helpers, each a small identity:

_normalize_newlines folds every CRLF and every bare CR to a lone LF, the exact
two-step replace vault_mirror._normalize and frontmatter.parse_frontmatter each
carry today. Extracting the identity means one place to reason about newline
handling as later bands (vault reader in M4.2, canon_check in M4.4) also read
mixed-origin text.

domain_prefix returns the "<name>/v1\\n" domain-separation string a sha256
digest scoping uses. R2's vault codec pins "canon-vault/v1\\n" (D-29); the M4
transport seam pins "canon-transport/v1\\n" (D-74). Both stay byte-stable across
runs and hosts. The helper refuses a shape a downstream parser could not
disambiguate: an empty name, a slash-bearing name, a newline-bearing name.
"""
from __future__ import annotations

_DOMAIN_SUFFIX = "/v1\n"


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def domain_prefix(name: str) -> str:
    if not isinstance(name, str):
        raise TypeError(
            f"domain prefix name must be str, got {type(name).__name__}")
    if not name:
        raise ValueError("domain prefix name must not be empty")
    if "/" in name:
        raise ValueError("domain prefix name must not contain '/'")
    if "\n" in name or "\r" in name:
        raise ValueError("domain prefix name must not contain a newline")
    return name + _DOMAIN_SUFFIX
