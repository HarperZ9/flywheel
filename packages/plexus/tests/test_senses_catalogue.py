"""The sense manifests are generated from SENSES.tsv and cannot drift from it."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from plexus import senses  # noqa: E402
from plexus.kinds import KINDS  # noqa: E402


def test_committed_manifests_are_in_step_with_the_table():
    assert senses.check() == []


def test_a_hand_edit_to_a_manifest_is_caught(tmp_path):
    tsv = tmp_path / "SENSES.tsv"
    shutil.copy(senses.TSV, tsv)
    mdir = tmp_path / "manifests"
    shutil.copytree(senses.MANIFEST_DIR, mdir)
    target = mdir / "quality.banding.interop.json"
    d = json.loads(target.read_text(encoding="utf-8"))
    d["sense"]["budget"]["time_s"] = 999
    target.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    (mdir / "stray.interop.json").write_text("{}\n", encoding="utf-8")
    (mdir / "gather.ocr.interop.json").unlink()
    problems = senses.check(str(tsv), str(mdir))
    assert "differs from SENSES.tsv: quality.banding.interop.json" in problems
    assert "not in SENSES.tsv: stray.interop.json" in problems
    assert "missing gather.ocr.interop.json" in problems


def test_a_table_edit_without_regeneration_is_caught(tmp_path):
    text = Path(senses.TSV).read_text(encoding="utf-8")
    tsv = tmp_path / "SENSES.tsv"
    tsv.write_text(text.replace("smooth tiles, banded share", "smooth tiles, banded portion"), encoding="utf-8")
    assert senses.check(str(tsv), senses.MANIFEST_DIR) == ["differs from SENSES.tsv: quality.banding.interop.json"]


def test_a_kind_outside_the_vocabulary_is_refused():
    text = Path(senses.TSV).read_text(encoding="utf-8")
    bad = text.replace("\timage\tsmooth tiles", "\tpicture-ish\tsmooth tiles", 1)
    with pytest.raises(senses.SensesError, match="not in the vocabulary"):
        senses.generate(bad)


def test_every_manifest_names_kinds_a_call_and_a_budget_when_runnable():
    mans = senses.load()
    assert len(mans) >= 60
    for m in mans:
        s = m.sense
        assert set(s["accepts"]) <= set(KINDS) and s["exact_call"] and s["verified"], m.organ
        if s["run"]:
            assert s["budget"]["time_s"] > 0 and s["budget"]["memory_mb"] > 0, m.organ
            assert ("cli" in s["run"]) != ("mcp" in s["run"]), m.organ
            assert s["run"]["forms"], m.organ


def test_no_local_paths_in_the_published_catalogue():
    text = Path(senses.TSV).read_text(encoding="utf-8")
    for m in senses.load():
        text += json.dumps(m.to_dict())
    import re
    assert not re.search(r"\b[A-Z]:[/\\]", text)
    assert "mission-control" not in text


def test_match_routes_by_kind_and_extension():
    mans = senses.load()
    image = {r["tool"] for r in senses.match(mans, ["file", "image"], ".png")}
    assert {"design_parts.measure_all", "quality.banding", "gather.decompose"} <= image
    assert "ear.listen" not in image
    assert "buildc.check" not in {r["tool"] for r in senses.match(mans, ["file", "code"], ".py")}
    assert "buildc.check" in {r["tool"] for r in senses.match(mans, ["file", "code"], ".bld")}
    assert senses.match(mans, [], "") == []
