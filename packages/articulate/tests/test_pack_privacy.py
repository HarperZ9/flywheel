"""The privacy pack: e-mail addresses and paths on one computer, each with a
control that must stay quiet, and the outbound profile's gate."""
import pytest

from articulate import checkext, domains, pack_privacy


def _run(text, profile="outbound"):
    r = checkext.check_text(text, profile=domains.load_profile(profile))
    hits = [f for f in r["high"] + r["medium"] + r["low"]
            if f["category"] in pack_privacy.CATEGORIES]
    return r, hits


@pytest.mark.parametrize("text, match", [
    ("Write to sam.lee@mailhost.zz for the draft.", "sam.lee@mailhost.zz"),
    (r"The notes sit in C:\dev\mission-control\notes.md today.", r"C:\dev\mission-control\notes.md"),
    ("The notes sit in C:/dev/mission-control today.", "C:/dev/mission-control"),
    ("Run it from /Users/sam/projects/site first.", "/Users/sam/projects/site"),
    ("It reads /home/sam/.config/app.toml at start.", "/home/sam/.config/app.toml"),
    (r"The share \\fileserver\team holds it.", r"\\fileserver\team"),
    ("```\ncd E:\\Downloads\\saves\n```\n", r"E:\Downloads\saves"),
    ("Open `D:/work/build` and run it.", "D:/work/build"),
])
def test_a_personal_detail_is_found_with_its_span(text, match):
    _r, hits = _run(text)
    assert [h["match"] for h in hits] == [match]


@pytest.mark.parametrize("text", [
    "Write to someone@example.com or ops@service.test for a sample.",
    "Replies go to noreply@service.io and 1234+name@users.noreply.github.com.",
    "See https://example.org/a:b/c and http://site.io/home/sam for details.",
    "The ratio is 3:1 and the time is 10:30/11:00.",
    "Run ./home/build or ~/Users/notes, which are relative.",
    "Call @handle on the forum.",
])
def test_controls_stay_quiet(text):
    _r, hits = _run(text)
    assert hits == []


def test_the_outbound_profile_gates_on_a_path():
    clean, _ = _run("The draft is ready for you to read.")
    leaky, _ = _run(r"The draft is in C:\Users\sam\draft.md for you to read.")
    assert clean["gate"] == "ok"
    assert leaky["gate"] == "blocked" and leaky["blocking_count"] == 1


@pytest.mark.parametrize("profile", ["note", "product-copy", "publication"])
def test_other_profiles_report_without_gating(profile):
    r, hits = _run("Reach me at sam.lee@mailhost.zz.", profile)
    assert [h["category"] for h in hits] == ["private-email"]
    assert r["gate"] == "ok"  # reported, not gating


def test_the_default_profile_does_not_run_the_pack():
    r = checkext.check_text(r"Reach me at sam.lee@mailhost.zz in C:\dev.")
    cats = [f["category"] for f in r["high"] + r["medium"] + r["low"]]
    assert not set(cats) & set(pack_privacy.CATEGORIES)
