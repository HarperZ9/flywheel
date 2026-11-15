"""Tests for the Field scalar-field primitive."""
from __future__ import annotations

import pytest

from coherence_membrane.field import Field, FieldKind


def test_field_constructs_and_indexes():
    f = Field(2, 2, FieldKind.LUMINANCE, (0.0, 0.25, 0.5, 1.0), (False,) * 4)
    assert f.at(0, 0) == 0.0
    assert f.at(1, 1) == 1.0
    assert f.is_unknown(0, 0) is False


def test_field_rejects_bad_value_length():
    with pytest.raises(ValueError):
        Field(2, 2, FieldKind.LUMINANCE, (0.0, 0.0), (False,) * 4)


def test_field_rejects_nonpositive_dims():
    with pytest.raises(ValueError):
        Field(0, 2, FieldKind.LUMINANCE, (), ())


def test_field_rejects_mismatched_unknown_length():
    # values length is correct (4) but unknown length is wrong (2) -> ValueError
    with pytest.raises(ValueError):
        Field(2, 2, FieldKind.LUMINANCE, (0.0, 0.25, 0.5, 1.0), (False, False))
