"""Falsifiers for a domain pack declared as a document.

The package ships three packs and the defect they catch is not confined to
three domains. A pack that arrives as a document has to earn the same trust the
shipped ones have, and the way it earns it is by being refused when it tries to
decide something. These tests are the refusals.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness.domain_packs import (PACKS, contract_from, declared_pack,
                                  load_pack, pack_report, read_pack, unsupplied)
from harness.domain_packs.declared import SCHEMA

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ROOT / "examples" / "output-validation" / "water-treatment.pack.json"

DOC = {
    "schema": SCHEMA,
    "name": "grid",
    "describes": "conductor sizing answers",
    "caution": "This pack holds no ampacity data and decides no rating.",
    "templates": {
        "ampacity": {"authority": "TABLE", "method": "table-with-correction",
                     "describes": "the rating the governing table gives",
                     "catches": "an uncorrected table figure used at "
                                "temperature"},
        "margin": {"authority": "BOUND", "criticality": "standard",
                   "catches": "a load inside the rating and outside the "
                              "design margin"},
    },
}


def _doc(**changes) -> dict:
    return dict(DOC, **changes)


def _one(**template) -> dict:
    return _doc(templates={"f": dict({"authority": "TABLE",
                                      "catches": "something"}, **template)})


def test_a_declared_pack_reaches_every_call_site_a_shipped_one_does(tmp_path):
    """The point of the loader. A domain nobody here has heard of builds a
    contract through the same two calls, with no registry to mutate first."""
    path = tmp_path / "grid.pack.json"
    path.write_text(json.dumps(DOC), encoding="utf-8")
    pack = load_pack(str(path))
    assert pack.name == "grid"
    contract = contract_from(pack, [{"use": "ampacity", "name": "ampacity",
                                     "source": "neca:table-310"}])
    assert contract[0]["authority"] == "TABLE"
    assert contract[0]["criticality"] == "critical"
    # And the pre-flight question still answers, which is what earns the pack.
    assert [gap["field"] for gap in unsupplied(contract, {})] == ["ampacity"]
    assert "holds no ampacity data" in pack_report(pack)


def test_a_declaration_may_not_carry_the_value_it_checks_against():
    """The rule the whole package rests on. A pack shipping a ceiling is the
    failure this feature catches, arriving as a config file."""
    for key in ("maximum", "limit", "rate", "table", "threshold", "daily_max"):
        with pytest.raises(ValueError) as exc:
            declared_pack(_one(**{key: 4.0}))
        assert key in str(exc.value)
    # A unit and a tolerance are properties of the check, so they pass.
    pack = declared_pack(_one(unit="A", tolerance=0.5))
    assert pack.templates["f"].unit == "A"
    assert pack.templates["f"].tolerance == 0.5


def test_a_declaration_may_not_take_a_shipped_pack_s_name():
    """Otherwise a reader of the resulting contract cannot tell whether the
    reviewed medicine pack decided it or a document on someone's disk did."""
    with pytest.raises(ValueError) as exc:
        declared_pack(_doc(name="medicine"), shipped=PACKS)
    assert "ships here" in str(exc.value)
    # Nothing is shadowed by construction: the shipped name still resolves.
    assert load_pack("medicine").name == "medicine"


def test_a_template_that_cannot_say_what_it_catches_is_refused():
    """A pack full of unarguable templates reads as coverage and checks
    nothing, and no reviewer can point at the line that is wrong."""
    with pytest.raises(ValueError) as exc:
        declared_pack(_doc(templates={"f": {"authority": "TABLE"}}))
    assert "what it catches" in str(exc.value)


def test_an_unreadable_key_is_refused_rather_than_ignored():
    """A key nothing reads is a key whose author expected something to happen.
    Dropping it silently would leave them believing it did."""
    with pytest.raises(ValueError) as exc:
        declared_pack(_one(criticallity="advisory"))
    assert "nothing reads" in str(exc.value)
    with pytest.raises(ValueError):
        declared_pack(_doc(fields={}))


def test_a_tolerance_that_is_not_a_number_is_refused():
    """`true` passes an int check in Python and would read as a tolerance of
    one, which on a current rating is not a tolerance at all."""
    with pytest.raises(ValueError) as exc:
        declared_pack(_one(tolerance=True))
    assert "not a number" in str(exc.value)
    with pytest.raises(ValueError):
        declared_pack(_one(authority="GUESS"))
    with pytest.raises(ValueError):
        declared_pack(_one(criticality="urgent"))


def test_a_declaration_without_a_caution_is_refused():
    """The caution is the line a reader acts on, and a pack whose author would
    not write one is a pack claiming more than it decides."""
    with pytest.raises(ValueError) as exc:
        declared_pack(_doc(caution="   "))
    assert "caution" in str(exc.value)
    for broken in (_doc(schema="something.else/v1"), _doc(name=""),
                   _doc(templates={}), ["not", "an", "object"]):
        with pytest.raises(ValueError):
            declared_pack(broken)


def test_a_malformed_document_is_a_refusal_not_a_pack_with_holes(tmp_path):
    """A pack that loaded with half its templates dropped would report a
    shorter contract as a passing one."""
    path = tmp_path / "torn.pack.json"
    path.write_text('{"schema": "flywheel.domain-pack-declar', encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        read_pack(path)
    assert "not readable as JSON" in str(exc.value)
    with pytest.raises(LookupError):
        load_pack("clippy")


def test_the_shipped_example_declares_a_domain_this_package_does_not():
    """Water is not one of the three, and it needs no code here to be checked.
    That is the whole claim the loader makes."""
    pack = read_pack(SHIPPED, shipped=PACKS)
    assert pack.name not in PACKS
    assert set(pack.templates) == {"dose", "dose_unit", "residual",
                                   "contact_time", "sample_point"}
    assert all(tpl.catches for tpl in pack.templates.values())
    # No value anywhere in the document, checked against the file rather than
    # against the object the loader built from it.
    raw = json.loads(SHIPPED.read_text(encoding="utf-8"))
    for spec in raw["templates"].values():
        assert not {"maximum", "limit", "table", "rate"} & set(spec)


def test_the_packs_command_reads_a_declaration_and_prints_the_refusal(tmp_path):
    def run(name):
        return subprocess.run([sys.executable, "-m", "harness.packs_cli", name],
                              capture_output=True, text=True, encoding="utf-8",
                              cwd=str(ROOT), check=False)

    good = run(str(SHIPPED))
    assert good.returncode == 0
    assert "holds no treatment data" in good.stdout

    path = tmp_path / "bad.pack.json"
    path.write_text(json.dumps(_one(maximum=1)), encoding="utf-8")
    bad = run(str(path))
    assert bad.returncode == 2
    assert "maximum" in bad.stdout
    assert "Traceback" not in bad.stderr
