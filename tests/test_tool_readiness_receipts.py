from scripts.run_tool_readiness_receipts import DEFAULT_TOOL_SET, build_report, profile_tool, split_names


def test_split_names_trims_empty_items():
    assert split_names("mneme, relay,,plexus ") == ["mneme", "relay", "plexus"]


def test_default_tool_set_covers_flagship_and_pubscan_tools():
    assert split_names(DEFAULT_TOOL_SET) == [
        "index",
        "forum",
        "gather",
        "crucible",
        "telos",
        "aleph",
        "mneme",
        "relay",
        "plexus",
        "pubscan",
    ]


def test_profile_tool_counts_static_surfaces_without_reading_contents(tmp_path):
    root = tmp_path / "mneme"
    (root / "src" / "mneme").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text("do-not-read", encoding="utf-8")
    (root / "README.md").write_text("do-not-read", encoding="utf-8")

    row = profile_tool("mneme", root)

    assert row["tool"] == "mneme"
    assert row["root_exists"] is True
    assert row["content_read"] is False
    assert row["enterprise_ready"] is False
    assert row["categories"]["core"]["present"] >= 4
    assert "SECURITY.md" in row["categories"]["enterprise"]["missing_files"]
    assert "do-not-read" not in str(row)


def test_build_report_marks_missing_tool_as_missing(tmp_path):
    report = build_report(
        tools=["mneme"],
        base_root=tmp_path,
        explicit_roots={},
    )

    assert report["schema"] == "harness.tool-readiness/v1"
    assert report["summary"]["tools"] == 1
    assert report["summary"]["missing_tools"] == 1
    assert report["tools"][0]["verdict"] == "TOOL_MISSING"
