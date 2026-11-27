"""Tests for the opt-in personal_email profile and its five deterministic AI-email tell checks."""
import contextlib
import io
import json

import pytest

from articulate import checkext, cli, detector, domains, pack_personal_email, profiles, project, receipt

HUMAN_REPLIES = [
    (
        "Hey Ohm,\n\n"
        "Sorry I missed Nov 25 on my end. We just brought a newborn home this month "
        "and my calendar slipped through the cracks. I am interested in hearing more "
        "about the RL environment work and the wet-lab setup. Would Monday or Tuesday "
        "afternoon Pacific time work for a quick call next week, say 1pm or 3pm PT?\n\n"
        "Zain\n"
    ),
    (
        "Hi Grace,\n\n"
        "Thanks for the note, and sorry for the slow reply. I am interested in the remote "
        "CUDA role. Most of my recent work has been writing custom single-GPU CUDA kernels "
        "alongside C++23 and DX12 compute shaders, all public on GitHub. What do the "
        "project scope and weekly hours look like, and do you have fifteen minutes early "
        "next week to talk through it?\n\n"
        "Zain\n"
    ),
    (
        "David,\n\n"
        "Short answer is we did not decompose that. Our scrape pulled the published "
        "summary tables across PDG 2010 to 2025 and CODATA 2002 to 2022 without the "
        "underlying per-experiment listings or dropped-paper flags. Splitting those two "
        "out would mean parsing the full input listings edition by edition, which is a "
        "much better question than what our table-level pass could answer.\n\n"
        "Zain\n"
    ),
    (
        "Johannes,\n\n"
        "No, we have not run that exact check yet. Our 0.287 came from a 252-treatment "
        "subset that kept first rounds only and dropped several experimental designs, "
        "which is why our own bar on the page flagged the 0.053 gap against your 0.234. "
        "If you want to point me to the exact inclusion filter or replication script, I "
        "am happy to re-run it cleanly and update the note.\n\n"
        "Zain\n"
    ),
]

PLANTED_AI_TELLS = [
    (
        "bulleted_personal_email",
        "Hi Alex,\n\nHere is my background:\n"
        "- Built a custom GPU compiler.\n"
        "- Published three local tools.\n"
        "- Shipped a test suite.\n\nZain\n",
    ),
    (
        "stiff_template_opener",
        "I hope this finds you well. I am reaching out to share my compiler repo "
        "and ask if your group takes external submissions.\n\nZain\n",
    ),
    (
        "stiff_template_opener",
        "Hello Grant team, I am a software engineer building local verification tools "
        "and would like to apply for the winter cycle.\n\nZain\n",
    ),
    (
        "enumeration_crutch",
        "Hi Sam,\n\nThree specific items for our call next week: scope, timeline, "
        "and benchmark inputs.\n\nZain\n",
    ),
    (
        "symmetrical_pr_closer",
        "Hi Maya,\n\nThe benchmark finished overnight and the log is attached. "
        "Thank you for your time and support. I am flexible on timing.\n\nZain\n",
    ),
    (
        "symmetrical_pr_closer",
        "Hi Maya,\n\nI sent the patch earlier today. "
        "Please let me know if you have any questions.\n\nZain\n",
    ),
    (
        "parenthetical_metric_stuffing",
        "Hi Jordan,\n\nWe shipped the audio rewrite yesterday "
        "(36/36 PASS, -14.8 LUFS, 126 Hz, 0 ms drift) and merged the branch.\n\nZain\n",
    ),
    (
        "parenthetical_metric_stuffing",
        "Hi Jordan,\n\nThe compiler suite passed (1,170 tests) and the site build "
        "finished cleanly (23/23 PASS) before noon.\n\nZain\n",
    ),
]


def _cats(result):
    return {f["category"] for tier in ("high", "medium", "low") for f in result[tier]}


def test_personal_email_profile_loads_and_promotes_all_five_categories():
    prof = domains.load_profile("personal_email")
    assert prof["domain"] == "personal_email"
    assert "personal_email" in prof["rule_packs"]
    assert set(pack_personal_email.CATEGORIES) <= set(prof["gate_promote"])


@pytest.mark.parametrize("expected_cat,sample", PLANTED_AI_TELLS)
def test_planted_ai_email_tells_are_blocked_fail_closed(expected_cat, sample):
    prof = domains.load_profile("personal_email")
    res = checkext.check_text(sample, profile=prof)
    assert expected_cat in _cats(res), f"{expected_cat} missed in {res}"
    assert res["gate"] == "blocked"
    assert res["blocking_count"] >= 1


@pytest.mark.parametrize("sample", HUMAN_REPLIES)
def test_clean_human_emails_pass_with_zero_email_flags(sample):
    prof = domains.load_profile("personal_email")
    res = checkext.check_text(sample, profile=prof)
    email_cats = set(pack_personal_email.CATEGORIES) & _cats(res)
    assert email_cats == set(), f"false positive on human reply: {email_cats}"
    assert res["gate"] == "ok"
    assert res["blocking_count"] == 0


def test_opt_in_isolation_and_cli_gate_and_tag_resolution(tmp_path):
    bad_note = PLANTED_AI_TELLS[0][1]
    # Opt-in: default flavored profile does not run personal_email checks
    plain = checkext.check_text(bad_note, profile=profiles.load("flavored"))
    assert "bulleted_personal_email" not in _cats(plain)
    assert plain["gate"] == "ok"

    # CLI --profile personal_email --gate exits 1 on planted AI email
    bad_path = tmp_path / "draft.md"
    bad_path.write_text(bad_note, encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(["check", str(bad_path), "--profile", "personal_email", "--json", "--gate"])
    assert rc == 1
    out = json.loads(buf.getvalue())["results"][0]
    assert out["profile"] == "personal_email"
    assert "bulleted_personal_email" in _cats(out)

    # In-file writing-profile tag resolves underscore profile name cleanly
    tagged = tmp_path / "reply.md"
    tagged.write_text("<!-- writing-profile: personal_email -->\n" + HUMAN_REPLIES[0],
                      encoding="utf-8")
    assert project.choose(str(tagged), tagged.read_text(encoding="utf-8"))[0] == "personal_email"
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = cli.main(["check", str(tagged), "--json", "--gate"])
    assert rc2 == 0
    assert json.loads(buf2.getvalue())["results"][0]["profile"] == "personal_email"


def test_personal_email_receipt_verifies_and_detects_tamper():
    text = HUMAN_REPLIES[1]
    rec = receipt.make_receipt(text, "personal_email", per_span=True)
    assert rec["profile"] == "personal_email"
    assert rec["gate"] == "ok"
    assert receipt.verify_receipt(rec, text)[0] == "Match"
    verdict, _detail = receipt.verify_receipt(
        rec, text + " Please let me know if you have any questions.\n"
    )
    assert verdict == "Unverifiable"
    # Pinned detector fingerprint stays untouched
    assert detector.check_text(text, profile=profiles.load("flavored"))["gate"] == "ok"
