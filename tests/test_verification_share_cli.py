"""`flywheel verify-share`: GitHub pull requests as shipped items, exit codes, packaging.

Success criteria: a pull request approved by someone other than its author is
person-checked, a self-approval is not; every check passing with at least one
success is machine, a failed or absent check is unchecked; family follows the
repository or the title prefix; a flagged week exits 1, a clean report 0, an
unreadable file 2; the command runs from the installed package.
"""
from __future__ import annotations

import io
import json

from harness.cli_entry import _PACKAGED
from harness.verification_share_cli import item_from_pr, main, pr_route

OK = [{"conclusion": "SUCCESS"}, {"conclusion": "SKIPPED"}]


def _pr(n=1, reviews=(), checks=OK, title="feat: x", day="2026-09-14", size=10, repo="o/r"):
    return {"number": n, "title": title, "mergedAt": f"{day}T10:00:00Z", "additions": size,
            "deletions": 0, "author": {"login": "me"}, "reviews": list(reviews),
            "statusCheckRollup": list(checks), "repository": repo}


def test_routes_from_reviews_and_checks():
    other = {"state": "APPROVED", "author": {"login": "you"}}
    mine = {"state": "APPROVED", "author": {"login": "me"}}
    assert pr_route(_pr(reviews=[other])) == "person"
    assert pr_route(_pr(reviews=[mine])) == "machine"
    assert pr_route(_pr(checks=OK + [{"conclusion": "FAILURE"}])) == "unchecked"
    assert pr_route(_pr(checks=[])) == "unchecked"
    assert pr_route(_pr(checks=[{"conclusion": "SKIPPED"}])) == "unchecked"
    assert pr_route(_pr(checks=[{"state": "SUCCESS"}])) == "machine"


def test_family_from_repo_or_prefix():
    assert item_from_pr(_pr(title="fix(cli): y")).family == "o/r"
    assert item_from_pr(_pr(title="fix(cli): y"), "prefix").family == "fix"
    assert item_from_pr(_pr(title="Add a thing"), "prefix").family == "other"


def _run(tmp_path, prs):
    f = tmp_path / "prs.json"
    f.write_text(json.dumps(prs), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    return main([str(f), "--github", "--json"], stdout=out, stderr=err), out.getvalue()


def test_flagged_week_exits_one(tmp_path):
    prs, n = [], 0
    for day, unchecked, checked in [("2026-09-07", 10, 90), ("2026-09-14", 30, 90), ("2026-09-21", 80, 100)]:
        prs.append(_pr(n, checks=[], day=day, size=unchecked)); n += 1
        prs.append(_pr(n, day=day, size=checked)); n += 1
    code, out = _run(tmp_path, prs)
    assert code == 1 and json.loads(out)["flags"][0]["week"] == "2026-W39"


def test_clean_report_exits_zero_and_unreadable_exits_two(tmp_path):
    assert _run(tmp_path, [_pr()])[0] == 0
    err = io.StringIO()
    assert main([str(tmp_path / "missing.json"), "--github"], stdout=io.StringIO(), stderr=err) == 2
    assert "cannot read" in err.getvalue()


def test_command_is_packaged():
    assert _PACKAGED["verify-share"] == "harness.verification_share_cli"
