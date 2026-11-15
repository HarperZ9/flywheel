"""The device readers, the devices command, the spoken view and graded survival.

Each device has a canonical example that must fire and a lookalike that must
not. The held-out rates live in corpus/core-devices; these tests pin behaviour
on named examples only, so a reader can improve without re-pinning a rate.
"""
import json
import pathlib

import pytest

from articulate import cli, devices, speech, survival

FIXTURE = pathlib.Path(__file__).parent / "data" / "core_devices" / "devices_v2.json"

CASES = [
    ("antithesis", "To err is human, to forgive divine.", "She was not hungry, but she ate the bread anyway."),
    ("antithesis", "The tool does not rewrite your text but marks where it reads as machine-written.",
     "I could not find the key, but the door was unlocked when I got there."),
    ("tricolon", "The tool is fast, simple and private.", "Ships left from Boston, Salem, and Newport that spring."),
    ("tricolon", "Government of the people, by the people, for the people, shall not perish.",
     "It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of foolishness."),
    ("anaphora", "Every receipt names its text. Every receipt names its ruleset. Every receipt can be replayed.",
     "The first step loads the file. The second step parses each line. The third step writes the report."),
    ("anaphora", "But we can not dedicate, we can not consecrate, we can not hallow this ground.",
     "Words, words, words."),
    ("chiasmus", "Ask not what the river owes you; ask what you owe the river.",
     "Ship the fix, then test the fix again tomorrow."),
    ("alliteration", "Peter Piper picked a peck of pickled peppers.", "The cat sat by the door all afternoon."),
    ("assonance", "Free trees need green leaves.", "The report was filed on time."),
    ("polysyndeton", "We ran and jumped and laughed and fell.", "Salt and pepper sat on the table by the window."),
    ("asyndeton", "I came, I saw, I conquered.", "Add the eggs, flour, and milk to the bowl."),
    ("anadiplosis", "The fix needs a test, and the test needs a reviewer.", "Read the draft. Then file it with the others."),
    ("epizeuxis", "Never, never, never give up the file.", "He said that that was fine."),
    ("isocolon", "Speech is silver, silence is golden.", "He did not call, but he wrote the next day after the meeting."),
    ("zeugma", "He took his hat and his leave.", "She lost her keys and her wallet."),
    ("oxymoron", "The hall fell into a deafening silence.", "The hall fell into a long silence."),
]


def _found(text):
    return {f["device"] for f in devices.analyze(text)["findings"]}


@pytest.mark.parametrize("device,positive,lookalike", CASES)
def test_each_device_fires_on_its_example_and_not_its_lookalike(device, positive, lookalike):
    assert device in _found(positive)
    assert device not in _found(lookalike)


def test_counts_cover_every_device_and_match_the_findings():
    r = devices.analyze("Peter Piper picked a peck of pickled peppers. We ran and jumped and fell and slept.")
    assert set(r["counts"]) == set(devices.DEVICES)
    assert sum(r["counts"].values()) == len(r["findings"])


def test_a_heading_never_runs_into_the_sentence_below():
    text = "# Every plan\n\nEvery plan needs a test. Every test needs a reader."
    assert "anaphora" not in _found(text)


def test_v2_fixture_is_well_formed():
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(fx["devices"]) == set(devices.DEVICES) == set(fx["definitions"])
    ids = [it["id"] for it in fx["items"]]
    assert len(ids) == len(set(ids))
    assert {it["split"] for it in fx["items"]} == {"dev", "heldout", "heldout-independent"}
    for it in fx["items"]:
        assert set(it["devices"]) <= set(fx["devices"]), it["id"]


def test_devices_command_lists_findings_and_speaks(tmp_path, capsys):
    f = tmp_path / "t.md"
    f.write_text("Free trees need green leaves.\n\nWe ran and jumped and laughed and fell.\n", encoding="utf-8")
    assert cli.main(["devices", str(f)]) == 0
    out = capsys.readouterr().out
    assert "assonance" in out and "polysyndeton" in out
    assert cli.main(["devices", str(f), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["polysyndeton"] == 1
    assert cli.main(["devices", str(f), "--speak", "--only", "polysyndeton"]) == 0
    spoken = capsys.readouterr().out
    assert spoken.startswith("1 finding.") and "Line 3" in spoken and "|" not in spoken
    assert cli.main(["devices", str(f), "--only", "nonsense"]) == 2


def test_ssml_is_well_formed_xml_and_escapes_text():
    import xml.dom.minidom
    text = "Fish & chips, fish & chips, fish & chips."
    doc = speech.ssml(devices.analyze(text)["findings"], text)
    xml.dom.minidom.parseString(doc)
    assert "&amp;" in doc


def test_check_speak_reads_findings_aloud(tmp_path, capsys):
    f = tmp_path / "t.md"
    f.write_text("The tool is not a detector but a style guide.\n", encoding="utf-8")
    cli.main(["check", str(f), "--speak"])
    out = capsys.readouterr().out
    assert "1 finding." in out and "Line 1" in out


def test_survival_grades_items_devices_rhythm_order_and_register():
    a = ("We must ship by 10 May. Every receipt names its text. Every receipt names its "
         "ruleset. Every receipt can be replayed.")
    b = "Every receipt can be replayed. We should ship by 12 May. Receipts name their text and ruleset."
    r = survival.compare(a, b)
    modal = [i for i in r["items"]["items"] if i["kind"] == "modal" and i["status"] == "changed"]
    assert modal and modal[0]["clarity"] == pytest.approx(0.7) and modal[0]["estimated"]
    assert r["items"]["kinds"]["number"] < 1
    assert r["devices"]["anaphora"]["clarity"] == 0.0
    assert 0 <= r["order"]["clarity"] < 1
    assert 0 < r["rhythm"]["clarity"] <= 1 and 0 < r["register"]["clarity"] <= 1


def test_survival_of_an_unchanged_text_is_complete():
    a = "Every receipt names its text. Every receipt names its ruleset. Every receipt can be replayed."
    r = survival.compare(a, a)
    assert all(v == 1.0 for v in r["items"]["kinds"].values())
    assert all(v["clarity"] == 1.0 for v in r["devices"].values())
    assert r["rhythm"]["clarity"] == 1.0 and r["order"]["clarity"] == 1.0
    assert r["register"]["clarity"] == 1.0


def test_a_device_the_rewrite_adds_reads_as_gain():
    r = survival.compare("We ran.", "We ran and jumped and laughed and fell.")
    assert r["devices"]["polysyndeton"] == {"before": 0, "after": 1, "clarity": None}
