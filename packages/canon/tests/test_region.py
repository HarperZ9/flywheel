"""region.py -- the byte-boundary layer of the R0 text surface.

extract_region partitions a managed file into (prefix, inner, suffix) with the
byte-exact invariant file == prefix + inner + suffix, finding the one canon
region by whole-line, column-0, CR-tolerant marker detection. splice_region
writes a new interior and leaves every byte outside the markers untouched.

These tests pin the outside-preservation guarantee on FILE BYTES (utf-8,
newline='' -- no universal-newline translation, no BOM strip), the exhaustive
boundary state machine (delta: end-without-begin named), and loud refusal of a
deformed or bad-scope marker rather than a silent off-limits.
"""
from __future__ import annotations

import pytest

from canon.region import RegionError, RegionSlice, extract_region, splice_region

BEGIN_W = "<!-- canon:begin scope=workspace -->"
BEGIN_G = "<!-- canon:begin scope=global -->"
END = "<!-- canon:end -->"
BLOCK = '<!-- canon:block id="x" -->'


def _region_lf(scope_begin: str = BEGIN_W) -> str:
    return (
        "top matter\n"
        f"{scope_begin}\n"
        f"{BLOCK}\n"
        "## X\n"
        "body\n"
        f"{END}\n"
        "tail matter\n"
    )


def test_extract_partitions_with_byte_exact_invariant() -> None:
    f = _region_lf()
    s = extract_region(f)
    assert isinstance(s, RegionSlice)
    assert s.present is True
    assert s.scope == "workspace"
    assert s.prefix + s.inner + s.suffix == f
    assert s.prefix.endswith(BEGIN_W + "\n")
    assert s.suffix.startswith(END + "\n")
    assert s.inner == f'{BLOCK}\n## X\nbody\n'


def test_splice_identity_law_lf() -> None:
    f = _region_lf()
    assert splice_region(f, extract_region(f).inner) == f


def test_splice_changes_only_interior() -> None:
    f = _region_lf()
    s = extract_region(f)
    out = splice_region(f, "REPLACED\n")
    assert out == s.prefix + "REPLACED\n" + s.suffix
    # prefix and suffix are byte-for-byte unchanged.
    assert out.startswith(s.prefix)
    assert out.endswith(s.suffix)


def test_outside_bytes_exact_crlf_host() -> None:
    raw = (
        "intro prose\r\n"
        f"{BEGIN_W}\r\n"
        f"{BLOCK}\r\n"
        "## X\r\n"
        "body\r\n"
        f"{END}\r\n"
        "outro\r\n"
    ).encode("utf-8")
    h = raw.decode("utf-8")
    s = extract_region(h)
    assert s.present is True
    assert s.scope == "workspace"
    # CR-tolerant marker match: the CRLF-terminated begin line is recognized.
    assert s.prefix.endswith(BEGIN_W + "\r\n")
    assert s.suffix.startswith(END + "\r\n")
    # Byte identity outside markers: decode->extract->splice->encode == raw.
    assert splice_region(h, s.inner).encode("utf-8") == raw


def test_outside_bytes_exact_bom_host() -> None:
    raw = (
        "﻿top matter\n"
        f"{BEGIN_G}\n"
        f"{BLOCK}\n"
        "## X\n"
        "body\n"
        f"{END}\n"
    ).encode("utf-8")
    h = raw.decode("utf-8")  # read as utf-8, never utf-8-sig
    s = extract_region(h)
    assert s.present is True
    assert s.prefix.startswith("﻿")  # BOM is ordinary prefix content
    assert splice_region(h, s.inner).encode("utf-8") == raw


def test_outside_bytes_exact_no_trailing_newline() -> None:
    f = (
        f"{BEGIN_G}\n"
        f"{BLOCK}\n## X\nbody\n"
        f"{END}"  # end marker is the final line, no trailing newline
    )
    s = extract_region(f)
    assert s.present is True
    assert s.suffix == END
    assert splice_region(f, s.inner) == f


def test_zero_markers_is_off_limits_not_error() -> None:
    f = "ordinary CLAUDE.md prose\nwith no markers at all\n"
    s = extract_region(f)
    assert s.present is False
    assert s.prefix == f and s.inner == "" and s.suffix == ""
    assert s.scope is None
    with pytest.raises(RegionError):
        splice_region(f, "anything\n")


@pytest.mark.parametrize(
    "f",
    [
        # two begins
        f"{BEGIN_W}\n{BEGIN_G}\n{END}\n",
        # two ends
        f"{BEGIN_W}\n{END}\n{END}\n",
        # end before begin
        f"{END}\n{BEGIN_W}\n",
        # begin without end
        f"{BEGIN_W}\n{BLOCK}\n## X\nbody\n",
        # end without begin (one end, zero begin) -- named explicitly
        f"stray\n{END}\ntail\n",
    ],
)
def test_illegal_marker_configurations_raise(f: str) -> None:
    with pytest.raises(RegionError):
        extract_region(f)


def test_indented_marker_is_loud_error() -> None:
    f = f"  {BEGIN_W}\n{BLOCK}\n## X\nbody\n{END}\n"
    with pytest.raises(RegionError):
        extract_region(f)


@pytest.mark.parametrize(
    "begin_line",
    [
        "<!-- canon:begin scope=repo -->",       # excluded scope
        "<!-- canon:begin -->",                   # missing scope
        '<!-- canon:begin scope="workspace" -->', # quoted, mimics sentinel style
    ],
)
def test_bad_scope_is_loud_error(begin_line: str) -> None:
    f = f"{begin_line}\n{BLOCK}\n## X\nbody\n{END}\n"
    with pytest.raises(RegionError):
        extract_region(f)


def test_midline_end_marker_in_suffix_is_not_a_boundary() -> None:
    f = (
        f"{BEGIN_G}\n{BLOCK}\n## X\nbody\n{END}\n"
        f"The terminator is {END} in prose.\n"
    )
    s = extract_region(f)
    assert s.present is True
    # whole-line anchoring ignores the mid-line occurrence; suffix bytes exact.
    assert f"The terminator is {END} in prose.\n" in s.suffix
    assert s.prefix + s.inner + s.suffix == f
