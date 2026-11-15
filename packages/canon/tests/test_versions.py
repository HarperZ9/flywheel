"""test_versions.py -- M4.3: the pin registry.

Covers SchemaPin construction, PIN_REGISTRY immutability, the five public
lookup functions, and the pin_registry_scope contextmanager. Migration seam
tests live in test_versions_migrate.py.
"""
from __future__ import annotations

import contextvars
import json
import re

import pytest

from canon.versions import (
    PIN_BACKEND_SEAM,
    PIN_DRIFT_VERDICT,
    PIN_FRONTMATTER,
    PIN_HANDOFF_RECEIPT,
    PIN_IMPORT_REPORT,
    PIN_PERSONA_THESIS_PAYLOAD,
    PIN_PROJECT_ID,
    PIN_PROJECT_ROW,
    PIN_RECONCILE_GATE_POLICY,
    PIN_RECORD,
    PIN_REGION_MARKER,
    PIN_REGISTRY,
    PIN_RENDER_LEDGER,
    PIN_RUN_WITNESS,
    PIN_TEXTBLOCK_GRAMMAR,
    PIN_TEXTUTIL,
    PIN_TRANSPORT_SEAM,
    PIN_VAULT_FRONTEND,
    PIN_VAULT_HUB_MARKER,
    PIN_VAULT_IDENTITY_DIGEST,
    PIN_VAULT_NOTE,
    PIN_WORKSPACE_STATE,
    PIN_WRITING_GATE_REGISTER,
    SEAM_PINS,
    MalformedPin,
    SchemaPin,
    UnknownPin,
    VersionError,
    all_pins,
    describe,
    is_compatible,
    pin_for,
    pin_from_schema_field,
    pin_registry_scope,
)

WAVE_ONE_NAMES = (
    "atom", "capsule", "omission", "transform-receipt",
    "readiness-probe", "bootstrap-witness", "adapter",
)

EVERY_CURRENT_SHORT_NAME = (
    "record", "backend-seam", "textblock-grammar", "region-marker",
    "frontmatter", "vault-note", "vault-identity-digest",
    "vault-hub-marker", "drift-verdict", "writing-gate-register",
    "persona-thesis-payload", "reconcile-gate-policy", "run-witness",
    "transport-seam", "vault-frontend", "textutil",
)


def test_pin_for_returns_schemapin():
    pin = pin_for("record")
    assert isinstance(pin, SchemaPin)
    assert pin.name == "record"
    assert pin.kind_tag == "canon.record/v1"


def test_pin_for_unknown_name_refuses():
    with pytest.raises(UnknownPin) as exc:
        pin_for("nope")
    assert "nope" in str(exc.value)


@pytest.mark.parametrize("name", WAVE_ONE_NAMES)
def test_pin_for_wave_one_names_all_refuse(name):
    with pytest.raises(UnknownPin):
        pin_for(name)


def test_every_registry_key_is_in_seam_pins():
    assert set(PIN_REGISTRY.keys()) == SEAM_PINS


@pytest.mark.parametrize("name", EVERY_CURRENT_SHORT_NAME)
def test_seam_pins_covers_every_current_seam(name):
    assert name in SEAM_PINS


def test_seam_pins_excludes_wave_one():
    assert SEAM_PINS.isdisjoint(set(WAVE_ONE_NAMES))


def test_all_pins_is_sorted_and_stable():
    first = all_pins()
    second = all_pins()
    assert first == second
    names = [p.name for p in first]
    assert names == sorted(names)
    assert len(first) == len(SEAM_PINS)


def test_pin_registry_is_immutable_from_outside_scope():
    with pytest.raises(TypeError):
        PIN_REGISTRY["record"] = SchemaPin(
            "record", "v1", "canon.record/v1", "spoof")  # type: ignore[index]


def test_pin_registry_populated_once_at_import():
    from canon import versions as v1
    from canon import versions as v2
    assert v1.PIN_REGISTRY is v2.PIN_REGISTRY


def test_is_compatible_exact_match():
    assert is_compatible(PIN_RECORD, PIN_RECORD) is True
    twin = SchemaPin("record", "v1", "canon.record/v1", "irrelevant-metadata")
    assert is_compatible(PIN_RECORD, twin) is True


def test_is_compatible_refuses_cross_version():
    other = SchemaPin("record", "v2", "canon.record/v2", "hypothetical")
    assert is_compatible(other, PIN_RECORD) is False


def test_is_compatible_refuses_cross_name():
    assert is_compatible(PIN_RECORD, PIN_FRONTMATTER) is False


@pytest.mark.parametrize("bad", ["v1", 1, None, ("record", "v1"), object()])
def test_is_compatible_refuses_non_pin(bad):
    with pytest.raises(MalformedPin):
        is_compatible(bad, PIN_RECORD)
    with pytest.raises(MalformedPin):
        is_compatible(PIN_RECORD, bad)


def test_pin_from_schema_field_round_trips_every_pin():
    for pin in all_pins():
        assert pin_from_schema_field(pin.kind_tag) is pin


def test_pin_from_schema_field_unknown_refuses():
    with pytest.raises(UnknownPin):
        pin_from_schema_field("canon.no-such-seam/v0")


@pytest.mark.parametrize("bad", [
    "record/v1", "canon.record", "canon.record/", "canon.RECORD/v1",
    "canon.record/1", "canon..record/v1", "canon.record/v01",
    "canon.record/v0-rc.1", "canon.record/v0+b", "",
])
def test_pin_from_schema_field_malformed_refuses(bad):
    with pytest.raises(MalformedPin):
        pin_from_schema_field(bad)


def test_pin_from_schema_field_non_str_refuses():
    with pytest.raises(MalformedPin):
        pin_from_schema_field(b"canon.record/v1")  # type: ignore[arg-type]


def test_describe_human_form():
    text = describe(PIN_RECORD)
    assert "record" in text
    assert "v1" in text
    assert "canon.record/v1" in text
    assert "F0 D-1" in text


def test_describe_json_form_is_byte_stable():
    first = describe(PIN_RECORD, form="json")
    second = describe(PIN_RECORD, form="json")
    assert first == second
    parsed = json.loads(first)
    assert parsed == {
        "name": "record", "version": "v1",
        "kind_tag": "canon.record/v1", "adr_ref": "F0 D-1",
    }


def test_describe_bad_form_raises_valueerror():
    with pytest.raises(ValueError):
        describe(PIN_RECORD, form="yaml")


def test_describe_non_pin_refuses():
    with pytest.raises(MalformedPin):
        describe("not-a-pin")  # type: ignore[arg-type]


def test_schemapin_is_frozen_and_hashable():
    with pytest.raises(Exception):
        PIN_RECORD.name = "spoof"  # type: ignore[misc]
    hash(PIN_RECORD)
    twin = SchemaPin("record", "v1", "canon.record/v1", "F0 D-1")
    assert twin == PIN_RECORD
    assert hash(twin) == hash(PIN_RECORD)


@pytest.mark.parametrize("bad_version", [
    "v01", "v0.01", "V1", "v0-rc.1", "v0+build.1",
    "1", "v", "", "v1.2.3", "v-1",
])
def test_schemapin_rejects_bad_version(bad_version):
    with pytest.raises(ValueError):
        SchemaPin("record", bad_version, f"canon.record/{bad_version}", "x")


def test_schemapin_rejects_v0_dot_0():
    with pytest.raises(ValueError):
        SchemaPin("textutil", "v0.0", "canon.textutil/v0.0", "x")


@pytest.mark.parametrize("bad_tag", [
    "record/v1", "canon.record", "canon.record/",
    "canon.RECORD/v1", "canon.record/1", "canon./v1", "",
])
def test_schemapin_rejects_bad_kind_tag(bad_tag):
    with pytest.raises(ValueError):
        SchemaPin("record", "v1", bad_tag, "x")


def test_schemapin_rejects_bad_name():
    with pytest.raises(ValueError):
        SchemaPin("not-a-known-seam", "v1", "canon.record/v1", "x")


def test_schemapin_rejects_kind_tag_version_mismatch():
    with pytest.raises(ValueError):
        SchemaPin("record", "v1", "canon.record/v2", "x")


def test_schemapin_rejects_empty_adr_ref():
    with pytest.raises(ValueError):
        SchemaPin("record", "v1", "canon.record/v1", "")


def test_schemapin_rejects_non_str_fields():
    with pytest.raises(ValueError):
        SchemaPin(123, "v1", "canon.record/v1", "x")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SchemaPin("record", 1, "canon.record/v1", "x")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SchemaPin("record", "v1", 123, "x")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SchemaPin("record", "v1", "canon.record/v1", 5)  # type: ignore[arg-type]


def test_pin_registry_scope_is_isolated():
    original_names = set(PIN_REGISTRY.keys())
    with pin_registry_scope() as scratch:
        with pytest.raises(ValueError):
            # A fake pin outside SEAM_PINS still refuses at construction.
            SchemaPin("fake-seam", "v0", "canon.fake-seam/v0", "test")
        scratch["record"] = SchemaPin(
            "record", "v1", "canon.record/v1", "OVERRIDDEN")
        assert pin_for("record").adr_ref == "OVERRIDDEN"
    assert pin_for("record").adr_ref == "F0 D-1"
    assert set(PIN_REGISTRY.keys()) == original_names


def test_pin_registry_scope_restores_on_exception():
    original = pin_for("record")
    with pytest.raises(RuntimeError, match="test-exc"):
        with pin_registry_scope() as scratch:
            scratch["record"] = SchemaPin(
                "record", "v1", "canon.record/v1", "SWAPPED-BEFORE-RAISE")
            assert pin_for("record").adr_ref == "SWAPPED-BEFORE-RAISE"
            raise RuntimeError("test-exc")
    assert pin_for("record") is original


def test_pin_registry_scope_uses_contextvars_not_threading():
    # A different contextvars.Context does not see this context's override.
    ctx = contextvars.copy_context()
    with pin_registry_scope() as scratch:
        scratch["record"] = SchemaPin(
            "record", "v1", "canon.record/v1", "OUTER-SET")
        seen_outer = pin_for("record").adr_ref
        seen_in_forked_ctx = ctx.run(lambda: pin_for("record").adr_ref)
    assert seen_outer == "OUTER-SET"
    assert seen_in_forked_ctx == "F0 D-1"


def test_pin_registry_scope_can_nest():
    with pin_registry_scope() as outer:
        outer["record"] = SchemaPin(
            "record", "v1", "canon.record/v1", "L1")
        assert pin_for("record").adr_ref == "L1"
        with pin_registry_scope() as inner:
            assert pin_for("record").adr_ref == "L1"
            inner["record"] = SchemaPin(
                "record", "v1", "canon.record/v1", "L2")
            assert pin_for("record").adr_ref == "L2"
        assert pin_for("record").adr_ref == "L1"
    assert pin_for("record").adr_ref == "F0 D-1"


def test_kinds_vocabulary_is_stable():
    from canon.schema import KINDS
    assert set(KINDS) == {
        "personality-block", "episodic-memory", "synthesized-persona-l3",
        "adr-decision", "research-artifact-ref",
    }


def test_scopes_vocabulary_is_stable():
    from canon.schema import SCOPES
    assert set(SCOPES) == {"global", "workspace"}


def test_vault_note_pin_and_vault_identity_digest_are_distinct():
    assert PIN_VAULT_NOTE.kind_tag == "canon.vault-note/v0"
    assert PIN_VAULT_IDENTITY_DIGEST.kind_tag == "canon.vault-identity-digest/v1"
    assert PIN_VAULT_NOTE != PIN_VAULT_IDENTITY_DIGEST
    assert PIN_VAULT_NOTE.version != PIN_VAULT_IDENTITY_DIGEST.version


def test_versions_module_imports_only_stdlib():
    import canon.versions as mod
    source = open(mod.__file__, encoding="utf-8").read()
    forbidden_imports = re.findall(
        r"^\s*(?:from|import)\s+([a-z_][a-zA-Z0-9_.]*)",
        source, flags=re.MULTILINE)
    stdlib_ok = {
        "__future__", "contextvars", "json", "re", "contextlib",
        "dataclasses", "types", "typing",
    }
    for name in forbidden_imports:
        root = name.split(".")[0]
        if root == "canon":
            continue  # canon-internal cross-module imports are fine
        assert root in stdlib_ok, \
            f"versions.py imports non-stdlib module {name!r}"


def test_error_hierarchy_is_two_roots():
    assert issubclass(UnknownPin, VersionError)
    assert issubclass(MalformedPin, VersionError)
    # IncompatiblePin is imported below via a local import to keep the module
    # header uncluttered.
    from canon.versions import IncompatiblePin
    assert issubclass(IncompatiblePin, VersionError)


def test_every_pin_constant_matches_its_registry_entry():
    constants = {
        "record": PIN_RECORD,
        "backend-seam": PIN_BACKEND_SEAM,
        "textblock-grammar": PIN_TEXTBLOCK_GRAMMAR,
        "region-marker": PIN_REGION_MARKER,
        "frontmatter": PIN_FRONTMATTER,
        "vault-note": PIN_VAULT_NOTE,
        "vault-identity-digest": PIN_VAULT_IDENTITY_DIGEST,
        "vault-hub-marker": PIN_VAULT_HUB_MARKER,
        "drift-verdict": PIN_DRIFT_VERDICT,
        "writing-gate-register": PIN_WRITING_GATE_REGISTER,
        "persona-thesis-payload": PIN_PERSONA_THESIS_PAYLOAD,
        "reconcile-gate-policy": PIN_RECONCILE_GATE_POLICY,
        "run-witness": PIN_RUN_WITNESS,
        "transport-seam": PIN_TRANSPORT_SEAM,
        "vault-frontend": PIN_VAULT_FRONTEND,
        "textutil": PIN_TEXTUTIL,
        "project-id": PIN_PROJECT_ID,
        "project-row": PIN_PROJECT_ROW,
        "workspace-state": PIN_WORKSPACE_STATE,
        "handoff-receipt": PIN_HANDOFF_RECEIPT,
        "import-report": PIN_IMPORT_REPORT,
        "render-ledger": PIN_RENDER_LEDGER,
    }
    assert set(constants) == SEAM_PINS
    for name, pin in constants.items():
        assert PIN_REGISTRY[name] is pin
        assert pin.name == name


def test_schema_module_pins_to_pin_record():
    """D-94: canon.schema.SCHEMA aliases PIN_RECORD.kind_tag through a
    bottom-of-module import. A downstream module that reads `SCHEMA` reads the
    same string as one that calls `pin_for('record').kind_tag`, byte-for-byte,
    with no fixture rewrite."""
    from canon.schema import SCHEMA
    assert SCHEMA is PIN_RECORD.kind_tag or SCHEMA == PIN_RECORD.kind_tag
    assert SCHEMA == "canon.record/v1"


def test_every_pin_has_a_recognized_adr_ref_shape():
    for pin in all_pins():
        assert pin.adr_ref, f"pin {pin.name} missing adr_ref"
        assert isinstance(pin.adr_ref, str)
