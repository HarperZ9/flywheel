"""Falsifiers for the command surface the domain packs added.

Three things a caller now depends on and none of them are covered by the
checker's own tests: a contract that names a pack instead of spelling out what
the domain already decides, a report that says whether the answer may leave the
building, and an exit code that carries that decision to a pipeline which
cannot hold a caveat in its head.
"""
import json

import pytest

from harness.cli_entry import _dispatch_packaged
from harness.contract_terms import (ADVISORY, CRITICAL, HOLD, RELEASE,
                                    STANDARD, TABLE)
from harness.output_check_cli import check, main, render, specs
from harness.packs_cli import as_json
from harness.packs_cli import main as packs_main
from harness.validation_ledger import read_ledger

BAND_LOOKUP = "formulary-band-lookup"
DOSE = {"use": "dose", "name": "dose", "source": "formulary:2026-03"}


# --- a contract that names a pack ------------------------------------------

def test_a_contract_with_no_pack_passes_its_fields_through():
    fields = [{"name": "tax", "authority": TABLE, "source": "t"}]
    assert specs({"fields": fields}) == fields


def test_a_pack_fills_in_what_the_domain_already_decides():
    """The document states the name and the source. Everything else is what a
    dose is, in medicine, regardless of who is asking."""
    (built,) = specs({"pack": "medicine", "fields": [DOSE]})
    assert built["authority"] == TABLE
    assert built["criticality"] == CRITICAL
    assert built["method"] == BAND_LOOKUP
    assert built["source"] == "formulary:2026-03"


def test_a_field_without_a_use_is_left_alone_beside_pack_fields():
    plain = {"name": "note", "authority": "CITED", "source": "s"}
    built = specs({"pack": "medicine", "fields": [DOSE, plain]})
    assert built[1] == plain


def test_an_override_beats_the_template_because_someone_wrote_it_down():
    """A pack sets criticality high on purpose. Lowering it is a decision, and
    a decision belongs in the contract document where a reader can see it."""
    (built,) = specs({"pack": "medicine",
                      "fields": [dict(DOSE, criticality=ADVISORY)]})
    assert built["criticality"] == ADVISORY


def test_an_unknown_template_is_refused_rather_than_silently_dropped():
    with pytest.raises(LookupError, match="no template"):
        specs({"pack": "medicine", "fields": [{"use": "posology",
                                               "name": "d", "source": "s"}]})


def test_an_unknown_pack_is_refused():
    with pytest.raises(LookupError, match="no domain pack"):
        specs({"pack": "astrology", "fields": [DOSE]})


def test_a_pack_contract_catches_an_answer_that_never_said_which_method(tmp_path):
    """The method mandate arrives with the pack, so a document that names one
    field gets a check nobody had to remember to write."""
    report = check({"pack": "medicine", "fields": [DOSE],
                    "authorities": {"formulary:2026-03": {"kind": "citation"}}},
                   {"dose": {"value": 600, "source": "formulary:2026-03"}},
                   base_dir=tmp_path, allow_commands=False)
    (row,) = report["fields"]
    assert row["code"] == "METHOD_UNSTATED"
    assert report["release"] == HOLD


# --- the release line ------------------------------------------------------

def test_the_release_line_names_what_blocks_it(tmp_path):
    report = check({"fields": [{"name": "dose", "authority": TABLE,
                                "source": "nowhere", "criticality": CRITICAL}],
                    "authorities": {"nowhere": {"kind": "citation"}}},
                   {}, base_dir=tmp_path, allow_commands=False)
    line = render(report).splitlines()[1]
    assert line.startswith(HOLD)
    assert "blocked by: dose" in line


def test_a_clean_report_says_release_and_blocks_nothing(tmp_path):
    contract, answer = _clean(tmp_path)
    report = check(json.loads(contract.read_text(encoding="utf-8")),
                   json.loads(answer.read_text(encoding="utf-8")),
                   base_dir=tmp_path, allow_commands=False)
    assert render(report).splitlines()[1] == RELEASE


# --- the exit codes --------------------------------------------------------

def _written(tmp_path, contract: dict, answer: dict):
    (tmp_path / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
    (tmp_path / "answer.json").write_text(json.dumps(answer), encoding="utf-8")
    return tmp_path / "contract.json", tmp_path / "answer.json"


def _clean(tmp_path):
    (tmp_path / "rows.json").write_text(json.dumps({"36700": 4169}),
                                        encoding="utf-8")
    return _written(
        tmp_path,
        {"fields": [{"name": "tax", "authority": TABLE, "source": "t"}],
         "authorities": {"t": {"kind": "table", "path": "rows.json",
                               "key_field": "taxable_income"}}},
        {"taxable_income": {"value": 36700, "source": "the return"},
         "tax": {"value": 4169, "source": "t"}})


def _held(tmp_path, criticality=CRITICAL):
    return _written(
        tmp_path,
        {"fields": [{"name": "dose", "authority": TABLE, "source": "nowhere",
                     "criticality": criticality}],
         "authorities": {"nowhere": {"kind": "citation"}}},
        {"dose": {"value": 600, "source": "nowhere"}})


def _run(paths, *extra):
    contract, answer = paths
    return main(["--contract", str(contract), "--answer", str(answer), *extra])


def test_a_held_answer_exits_three_on_the_verdict_and_one_under_strict(tmp_path):
    """Same run, two readers. One asks whether the values are confirmed and is
    told nothing confirmed them. One asks whether this may ship and is told no.
    """
    held = _held(tmp_path)
    assert _run(held) == 3
    assert _run(held, "--strict") == 1


def test_a_caveat_is_not_promoted_to_a_failure_by_strict(tmp_path):
    """Strict raises the bar on release, not on the verdict. A standard field
    nobody could check is still unverified rather than wrong."""
    assert _run(_held(tmp_path, STANDARD), "--strict") == 3


def test_strict_leaves_a_clean_release_alone(tmp_path):
    clean = _clean(tmp_path)
    assert _run(clean) == 0
    assert _run(clean, "--strict") == 0


# --- the ledger flags ------------------------------------------------------

def test_a_scope_and_subject_put_the_check_in_the_ledger(tmp_path):
    ledger = tmp_path / "v.jsonl"
    assert _run(_held(tmp_path), "--ledger", str(ledger),
                "--scope", "goal", "--subject", "g-2") == 3
    (entry,) = read_ledger(ledger)
    assert entry["scope"] == "goal"
    assert entry["subject"] == "g-2"
    assert entry["release"] == HOLD


def test_no_ledger_flags_writes_no_ledger(tmp_path, monkeypatch):
    """The default is a check that leaves no trace, because a command a person
    runs to look at one answer should not accumulate a record of them."""
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    _run(_held(tmp_path))
    assert read_ledger() == []


def test_an_unknown_scope_is_a_usage_error_not_a_verdict(tmp_path):
    """Argparse owns two. A harness that read a mistyped scope as an unverified
    answer would retry the whole task."""
    with pytest.raises(SystemExit) as exit_info:
        _run(_held(tmp_path), "--scope", "quarter")
    assert exit_info.value.code == 2


# --- flywheel packs --------------------------------------------------------

def test_the_listing_leads_with_the_line_that_matters(capsys):
    assert packs_main([]) == 0
    printed = capsys.readouterr().out
    assert "no domain data" in printed
    for name in ("finance", "law", "medicine"):
        assert name in printed


def test_a_pack_report_prints_the_caution_before_the_templates(capsys):
    assert packs_main(["medicine"]) == 0
    printed = capsys.readouterr().out
    assert printed.index("holds no clinical data") < printed.index("dose_unit")


def test_every_template_says_what_it_catches():
    for template in as_json("law")["templates"]:
        assert template["catches"]


def test_an_unknown_pack_name_exits_two_rather_than_printing_nothing(capsys):
    assert packs_main(["astrology"]) == 2
    assert "known:" in capsys.readouterr().out


def test_the_json_form_is_what_a_harness_reads(capsys):
    assert packs_main(["finance", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "finance"
    assert payload["caution"]


def test_flywheel_packs_reaches_the_packaged_command(capsys):
    """The dispatch, not the module. A command the docs tell a reader to run
    has to resolve from the umbrella entry point."""
    assert _dispatch_packaged("packs", ["packs", "law"]) == 0
    assert "law:" in capsys.readouterr().out
