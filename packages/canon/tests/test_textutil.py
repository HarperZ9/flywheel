"""test_textutil.py -- shared text helpers used by every M4 seam.

_normalize_newlines is the newline-folding step vault_mirror._normalize and
frontmatter.parse_frontmatter each carry today. Extracting the identity means one
place to reason about CRLF/CR handling. domain_prefix is the domain-separation
step the transport idempotency key uses (proposal line 129) and that R2's vault
digest already uses (canon-vault/v1\\n at src/canon/vault.py). Both helpers stay
pure, stdlib-only, no ambient clock, no I/O.
"""
from __future__ import annotations

import inspect

from canon import textutil


def test_normalize_newlines_folds_crlf_to_lf():
    assert textutil._normalize_newlines("a\r\nb\r\nc") == "a\nb\nc"


def test_normalize_newlines_folds_bare_cr_to_lf():
    assert textutil._normalize_newlines("a\rb\rc") == "a\nb\nc"


def test_normalize_newlines_leaves_lone_lf_unchanged():
    assert textutil._normalize_newlines("a\nb\nc") == "a\nb\nc"


def test_normalize_newlines_handles_mixed_endings():
    assert textutil._normalize_newlines("a\r\nb\rc\nd") == "a\nb\nc\nd"


def test_normalize_newlines_empty_string_is_empty():
    assert textutil._normalize_newlines("") == ""


def test_normalize_newlines_only_newlines():
    # \r\n counts as one boundary; \r alone counts as one; \n alone counts as one.
    assert textutil._normalize_newlines("\r\n\r\n") == "\n\n"
    assert textutil._normalize_newlines("\r\r") == "\n\n"
    assert textutil._normalize_newlines("\n\n") == "\n\n"


def test_normalize_newlines_preserves_unicode():
    assert textutil._normalize_newlines("é\r\nñ\r漢") == "é\nñ\n漢"


def test_normalize_newlines_matches_vault_mirror_current_behavior():
    # The vault_mirror._normalize helper today does the identical two-step
    # replace. Extracting a shared implementation must not shift bytes.
    from canon import vault_mirror

    samples = [
        "",
        "no boundary",
        "unix\nunix\n",
        "mac\rmac\r",
        "win\r\nwin\r\n",
        "mixed\r\nmac\rline\nend",
        "trailing\r\n",
        "leading\r\nrest",
    ]
    for s in samples:
        assert textutil._normalize_newlines(s) == vault_mirror._normalize(s)


def test_normalize_newlines_matches_frontmatter_current_behavior():
    # frontmatter.parse_frontmatter runs the same replace inline at line 103.
    # The extracted helper must produce the same bytes for any input.
    samples = [
        "one\r\ntwo\r\n",
        "one\rtwo\r",
        "one\ntwo",
        "\r\n",
    ]
    for s in samples:
        expected = s.replace("\r\n", "\n").replace("\r", "\n")
        assert textutil._normalize_newlines(s) == expected


def test_domain_prefix_canon_transport_matches_proposal_string():
    # Proposal line 129 fixes this exact byte sequence for the transport
    # idempotency key. A drift here is a wire-shape change.
    assert textutil.domain_prefix("canon-transport") == "canon-transport/v1\n"


def test_domain_prefix_canon_vault_matches_r2_domain():
    # R2 D-29 pins the vault digest domain to "canon-vault/v1\n". The extracted
    # helper must reconstruct that same prefix byte-for-byte so the vault code
    # can adopt it without a wire change.
    assert textutil.domain_prefix("canon-vault") == "canon-vault/v1\n"


def test_domain_prefix_shape_is_name_slash_v1_lf():
    for name in ["canon-transport", "canon-vault", "canon-x"]:
        got = textutil.domain_prefix(name)
        assert got.startswith(name + "/v1")
        assert got.endswith("\n")
        assert got == f"{name}/v1\n"


def test_domain_prefix_refuses_empty_name():
    # An empty domain would collapse two seams' key spaces. Refuse loud.
    try:
        textutil.domain_prefix("")
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty name")


def test_domain_prefix_refuses_name_with_slash():
    # A slash inside the name would ambiguate the "/v1" separator on parse.
    try:
        textutil.domain_prefix("canon/transport")
    except ValueError:
        return
    raise AssertionError("expected ValueError for slash-bearing name")


def test_domain_prefix_refuses_name_with_newline():
    # A newline would corrupt the domain-separation guarantee at scan time.
    try:
        textutil.domain_prefix("canon\ntransport")
    except ValueError:
        return
    raise AssertionError("expected ValueError for newline-bearing name")


def test_domain_prefix_refuses_non_str_name():
    try:
        textutil.domain_prefix(b"canon-transport")  # type: ignore[arg-type]
    except TypeError:
        return
    raise AssertionError("expected TypeError for bytes name")


def test_textutil_imports_only_stdlib():
    # M4 must not sneak a runtime dep in through the helpers. Enforce the
    # invariant on the module's imports.
    src = inspect.getsource(textutil)
    for banned in (
        "import requests",
        "import httpx",
        "import urllib.request",
        "import socket",
        "import ssl",
        "import pickle",
        "import typing_extensions",
    ):
        assert banned not in src, f"textutil must not {banned}"


def test_textutil_functions_have_no_time_default():
    # No ambient time.time() default in any signature (proposal honest null).
    for name in ("_normalize_newlines", "domain_prefix"):
        fn = getattr(textutil, name)
        for param in inspect.signature(fn).parameters.values():
            if param.default is inspect.Parameter.empty:
                continue
            assert "time" not in repr(param.default).lower(), (
                f"{name} default {param.default!r} looks time-ish")
