from scripts.run_gather_readiness import build_report, profile_gather, split_paths


def test_split_paths_handles_empty_items():
    assert [str(path) for path in split_paths("C:/a;;C:/b")] == ["C:/a", "C:/b"]


def test_profile_gather_reports_static_surfaces_without_reading_configs(tmp_path, monkeypatch):
    gather = tmp_path / "gather"
    (gather / "src" / "gather").mkdir(parents=True)
    (gather / "tests").mkdir()
    (gather / "README.md").write_text("do-not-read", encoding="utf-8")
    (gather / "src" / "gather" / "discord.py").write_text("do-not-read", encoding="utf-8")
    (gather / "src" / "gather" / "run_config.py").write_text("do-not-read", encoding="utf-8")
    (gather / "src" / "gather" / "method.py").write_text("do-not-read", encoding="utf-8")
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "gather-discord.json").write_text('{"secret":"do-not-read"}', encoding="utf-8")
    monkeypatch.delenv("GATHER_DISCORD_BOT_TOKEN", raising=False)

    row = profile_gather(
        gather_root=gather,
        config_roots=[configs],
        config_pattern="gather-*.json",
        credential_vars=["GATHER_DISCORD_BOT_TOKEN"],
        max_configs=20,
    )

    assert row["root_exists"] is True
    assert row["content_read"] is False
    assert row["config_count"] == 1
    assert row["credentials"]["GATHER_DISCORD_BOT_TOKEN"] is False
    assert row["verdict"] == "GATHER_STATIC_READY_NEEDS_CREDENTIAL"
    assert "do-not-read" not in str(row)


def test_build_report_marks_missing_gather_as_missing(tmp_path):
    report = build_report(
        gather_root=tmp_path / "missing",
        config_roots=[],
        config_pattern="gather-*.json",
        credential_vars=["GATHER_DISCORD_BOT_TOKEN"],
        max_configs=20,
    )

    assert report["schema"] == "harness.gather-readiness/v1"
    assert report["summary"]["root_exists"] is False
    assert report["summary"]["verdict"] == "GATHER_MISSING"
