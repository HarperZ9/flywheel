"""The Python reader of lean4export files, and the tool pins.

harness/lean_ndjson.py fingerprints the statement the external kernel
checked; harness/lean_external_tools.py refuses a tool that is not the pinned
build. Both are pure Python, so these always run.
"""
import json

import pytest
from _lean_external_fixture import export

from harness import lean_external_tools as tools
from harness.lean_ndjson import Export, ExportError, meaning_mismatches

META = {"meta": {"exporter": {"name": "lean4export", "version": "3.1.0"},
                 "format": {"version": "3.1.0"},
                 "lean": {"githash": "g", "version": "4.34.1"}}}


def _forall(binder: str, info: str, mdata: bool = False) -> Export:
    """∀ (x : Prop), x  as an export, with the binder named and marked."""
    rows = [META, {"in": 1, "str": {"pre": 0, "str": binder}},
            {"in": 2, "str": {"pre": 0, "str": "t"}},
            {"ie": 0, "sort": 0}, {"ie": 1, "bvar": 0}]
    body = 1
    if mdata:
        rows.append({"ie": 2, "mdata": {"expr": 1, "data": {}}})
        body = 2
    rows.append({"ie": 3, "forallE": {"name": 1, "type": 0, "body": body,
                                      "binderInfo": info}})
    rows.append({"axiom": {"name": 2, "levelParams": [], "type": 3,
                           "isUnsafe": False}})
    return Export("\n".join(json.dumps(r) for r in rows))


def test_the_statement_hash_is_alpha_invariant():
    a = _forall("x", "default").statement_sha256("t")
    assert a == _forall("y", "implicit").statement_sha256("t")
    assert a == _forall("x", "default", mdata=True).statement_sha256("t")
    assert len(a) == 64


def test_a_different_statement_hashes_differently():
    t = Export(export("t", "g")).statement_sha256("t")
    assert t != Export(export("t", "g", prop="False")).statement_sha256("t")
    assert Export(export("t", "g")).statement_sha256("absent") == ""


@pytest.mark.parametrize("text, why", [
    ("", "empty"), ("not json", "not JSON"), ("[1]", "not a JSON object"),
    (json.dumps({"mystery": 1}), "unknown record"),
    (export("t", "g").replace('"3.1.0"}, "lean"', '"3.2.0"}, "lean"'),
     "outside"),
    (json.dumps(META) + "\n" + json.dumps({"ie": 0, "app": {"fn": 5,
                                                             "arg": 6}}),
     "malformed")])
def test_an_unreadable_export_is_refused_by_name(text, why):
    with pytest.raises(ExportError, match=why):
        Export(text)


def test_meaning_mismatch_follows_the_challenge_s_definitions():
    same = Export(export("t", "g"))
    assert meaning_mismatches(same, Export(export("t", "g")), "t") == []
    other = Export(export("t", "g").replace('"numNested": 0',
                                            '"numNested": 1'))
    assert meaning_mismatches(other, same, "t") == [
        "True differs between the candidate and the challenge"]
    assert meaning_mismatches(same, same, "absent") == [
        "the challenge export holds no absent"]


# --- the pinned tools --------------------------------------------------------

def _provision(tmp_path, **override):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    entries = {}
    for key, pin in tools.PINS.items():
        binary = bindir / f"{key}.bin"
        binary.write_bytes(key.encode())
        entries[key] = dict(pin, binary=str(binary),
                            binary_sha256=tools.sha256_file(binary))
        entries[key].update(override.get(key, {}))
    (tmp_path / tools.MANIFEST).write_text(json.dumps(
        {"schema": tools.SCHEMA, "tools": entries}), encoding="utf-8")
    return tmp_path


def test_intact_pinned_tools_resolve(tmp_path):
    found, why = tools.resolve(_provision(tmp_path))
    assert why == "" and set(found) == {"nanoda", "lean4export"}
    rec = tools.record(found)
    assert rec["source_commit"] == tools.PINS["nanoda"]["commit"]
    assert str(tmp_path) not in json.dumps(rec)     # no local path


@pytest.mark.parametrize("override, why", [
    ({"nanoda": {"commit": "0" * 40}}, "commit"),
    ({"lean4export": {"version": "v4.35.0"}}, "version"),
    ({"nanoda": {"archive_sha256": "f" * 64}}, "archive_sha256"),
    ({"nanoda": {"binary_sha256": "0" * 64}}, "does not match"),
    ({"lean4export": {"binary": "relative/lean4export"}}, "not a file")])
def test_a_tool_off_its_pin_is_refused(tmp_path, override, why):
    found, reason = tools.resolve(_provision(tmp_path, **override))
    assert found == {} and why in reason


def test_no_manifest_names_the_provisioning_script(tmp_path):
    found, why = tools.resolve(tmp_path)
    assert found == {} and "provision_external_kernel" in why


def test_the_tools_dir_follows_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_EXTERNAL_KERNEL_DIR", str(tmp_path))
    assert tools.tools_dir() == tmp_path
    monkeypatch.delenv("FLYWHEEL_EXTERNAL_KERNEL_DIR")
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    assert tools.tools_dir() == tmp_path / "tools" / "external-kernel"
