"""`check --sarif` output validates against the SARIF 2.1.0 schema, and
`--content-free` removes every matched substring and every offset.

The schema in tests/data/sarif-schema-2.1.0.json is the OASIS SARIF 2.1.0
schema, downloaded on 23 October 2026 from
https://json.schemastore.org/sarif-2.1.0.json (its id names
https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json),
sha256 c96eb2d311c37b0a38cbd18c52d79a68f778bbd2d831abed7412d9850740f785.
"""
import hashlib
import json
import pathlib

import pytest

from articulate import cli

jsonschema = pytest.importorskip("jsonschema")

SCHEMA = pathlib.Path(__file__).parent / "data" / "sarif-schema-2.1.0.json"
SCHEMA_SHA256 = "c96eb2d311c37b0a38cbd18c52d79a68f778bbd2d831abed7412d9850740f785"
TEXT = ("It is crucial to note that we must delve into the tapestry of results. "
        "Moreover, the build runs at night — and it is robust.\n\n"
        "The team ships on Friday. Furthermore, we leverage a seamless pipeline.\n")


def _run(capsys, *args):
    capsys.readouterr()
    cli.main(["check", *args])
    return capsys.readouterr().out


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text(TEXT, encoding="utf-8")
    return path


def _validate(doc):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)
    errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(doc), key=str)
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors[:5]]


def test_vendored_schema_is_the_recorded_file():
    assert hashlib.sha256(SCHEMA.read_bytes()).hexdigest() == SCHEMA_SHA256


@pytest.mark.parametrize("extra", [[], ["--content-free"]])
def test_sarif_output_validates_against_the_schema(capsys, sample, extra):
    doc = json.loads(_run(capsys, str(sample), "--sarif", *extra))
    assert doc["runs"][0]["results"], "the sample must produce findings"
    _validate(doc)


def test_sarif_artifact_uri_is_a_uri(capsys, sample):
    doc = json.loads(_run(capsys, str(sample), "--sarif"))
    uri = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri.startswith("file:///") and uri.endswith("/sample.md"), uri
    assert "\\" not in uri


def test_relative_path_stays_relative(capsys, sample, monkeypatch):
    monkeypatch.chdir(sample.parent)
    doc = json.loads(_run(capsys, "sample.md", "--sarif"))
    assert doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "sample.md"


def test_content_free_sarif_carries_no_matched_text_or_offsets(capsys, sample):
    found = json.loads(_run(capsys, str(sample), "--json"))["results"][0]
    matches = {f["match"] for tier in ("high", "medium", "low") for f in found.get(tier, [])
               if f.get("match") and len(f["match"].strip()) > 1}
    assert matches, "the sample must produce matched text"
    text = _run(capsys, str(sample), "--sarif", "--content-free")
    # A rule id names the rule's own word list (for example
    # "corporate-verb/leverage-underscore-reflect-as-corporate-verb"), and
    # --content-free keeps rule ids by design, so compare against the output
    # with the rule ids removed.
    doc = json.loads(text)
    ids = {r["id"] for r in doc["runs"][0]["tool"]["driver"]["rules"]}
    for rid in ids:
        text = text.replace(rid, "")
    leaked = sorted(m for m in matches if m in text or json.dumps(m)[1:-1] in text)
    assert not leaked, leaked
    for result in json.loads(text)["runs"][0]["results"]:
        region = result["locations"][0]["physicalLocation"]["region"]
        assert set(region) == {"startLine"}, region
