"""Every bundled lane is a published release, or the notice says it is not.

Correctness review F6, security review 9 and product-truth review PT-7 of
1.1.0: the index payload row pins 71c26eab, one commit past the v2.13.0 tag
(``owner_describe`` v2.13.0-1-g71c26ea), and four of its files differ from
the PyPI 2.13.0 sdist that pip, source installs and CI get. The shipped
notice said "tag v2.13.0 @ 71c26eabde26", which reads as the tag.

- A row whose ``owner_describe`` is not its tag (the pin is not the tagged
  release) must be listed in ``UNRELEASED`` with that exact describe, and its
  notice line must name the describe and say no release contains it.
- A listed row that becomes a tagged release again fails, so the list cannot
  go stale after a repin.
"""
from __future__ import annotations

import json
from pathlib import Path

from harness.lanes_registry import LANES

ROOT = Path(__file__).resolve().parents[1]
ROWS = [json.loads(line) for line in (ROOT / "packaging" / "python-lane-payloads.jsonl")
        .read_text(encoding="utf-8").splitlines() if line.strip()]
NOTICE = (ROOT / "desktop" / "release" / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")

#: Rows pinned past their tag, reviewed and disclosed. Cutting a release that
#: contains the pinned commit and repinning to its tag removes the entry (index:
#: 2.14.0 contains 71c26eab; repin once PyPI serves it).
UNRELEASED = {"index": "v2.13.0-1-g71c26ea"}


def _line(row: dict) -> str:
    head = f"{row['registry_install_name']} {row['flywheel_registry_expected_version']} " \
           f"(lane {row['lane']}), "
    if row["owner_describe"] == row["owner_tag"]:
        return head + f"tag {row['owner_tag']} @ {row['owner_commit'][:12]}"
    return head + (f"{row['owner_describe']} @ {row['owner_commit'][:12]}, one commit "
                   f"past tag {row['owner_tag']}; no release contains it")


def test_every_row_is_its_tagged_release_unless_listed():
    for row in ROWS:
        lane = row["lane"]
        assert row["owner_tag"] == "v" + LANES[lane].version, lane
        if lane in UNRELEASED:
            assert row["owner_describe"] == UNRELEASED[lane], lane
            assert row["owner_describe"] != row["owner_tag"], (
                f"{lane} is a tagged release again; drop it from UNRELEASED")
        else:
            assert row["owner_describe"] == row["owner_tag"], (
                f"{lane} pins {row['owner_describe']}, not a release; cut one or list it")


def test_the_notice_names_each_row_as_it_is():
    for row in ROWS:
        assert _line(row) in NOTICE, _line(row)


def test_the_notice_header_does_not_promise_a_tag_for_every_line():
    assert "at the tag named." not in NOTICE
    assert "at the tag or commit named" in NOTICE
