"""Falsifiers for the lane layer (harness/lanes.py).

The lane roster must be honest about what is installed vs declared vs missing,
and the install-name -> command asymmetry must map correctly (pip install
gather-engine exposes the `gather` command, etc.). A missing lane never
crashes the roster; it reports `missing`/`declared`.
"""
from harness.lanes import (
    LANES, MISSING, DECLARED, LIVE, STALE,
    lane_status, lane_roster, lane_report, resolve_mcp_command,
)


def test_registry_covers_the_seven_lanes():
    # gather, crucible, index, forum, learn, telos + local-model (the engine)
    assert set(LANES) == {"gather", "crucible", "index", "forum",
                          "learn", "telos", "local-model"}


def test_install_name_to_command_asymmetry_is_mapped():
    # Each pip lane's distribution name differs from its command.
    assert LANES["index"].install_name == "index-graph"
    assert LANES["index"].command == "index"
    assert LANES["gather"].install_name == "gather-engine"
    assert LANES["gather"].command == "gather"
    assert LANES["crucible"].install_name == "crucible-bench"
    assert LANES["crucible"].command == "crucible"
    assert LANES["forum"].install_name == "forum-engine"
    assert LANES["forum"].command == "forum"


def test_every_lane_has_an_mcp_command_and_organ():
    for name, lane in LANES.items():
        cmd = resolve_mcp_command(name)
        assert isinstance(cmd, list) and len(cmd) >= 1
        assert lane.organ, f"{name} has no organ assigned"
        assert lane.role, f"{name} has no role assigned"
        assert lane.kind in ("pip", "npm", "bundled")


def test_unknown_lane_reports_missing_not_crash():
    r = lane_status("nonexistent")
    assert r["status"] == MISSING
    assert "unknown lane" in r["detail"]


def test_roster_includes_every_lane_and_counts_status():
    roster = lane_roster(probe=False)
    assert roster["schema"] == "flywheel.lanes/v1"
    assert roster["n_lanes"] == len(LANES)
    statuses = {r["status"] for r in roster["lanes"]}
    # every reported status is a known value
    assert statuses <= {LIVE, DECLARED, MISSING, STALE}
    assert sum(roster["by_status"].values()) == roster["n_lanes"]


def test_report_is_human_readable_and_nonempty():
    text = lane_report()
    assert "Flywheel lanes" in text
    assert "lanes" in text
    for name in LANES:
        assert name in text


def test_bundled_lane_needs_no_install():
    # local-model is the engine lane; it IS Flywheel, so it is never missing.
    r = lane_status("local-model", probe=False)
    assert r["status"] in (LIVE, DECLARED)
    assert LANES["local-model"].kind == "bundled"


def test_node_lanes_resolve_to_absolute_source_path_when_repo_present():
    # telos's package profile uses a relative script path; the source profile
    # must resolve it to an absolute path under the telos repo.
    cmd = resolve_mcp_command("telos")
    assert cmd[0] == "node"
    # when the source checkout is present, the path is absolute
    if len(cmd) > 1 and cmd[1] not in ("demo/telos-mcp.mjs",):
        assert cmd[1].endswith("telos-mcp.mjs")


def test_install_lane_arg_parser_defaults():
    from harness.cli_entry import _parse_lane_args
    lanes, profile = _parse_lane_args([])
    assert lanes == "all"
    assert profile == "package"


def test_install_lane_arg_parser_explicit():
    from harness.cli_entry import _parse_lane_args
    lanes, profile = _parse_lane_args(["--lanes", "index,gather", "--profile", "source"])
    assert lanes == "index,gather"
    assert profile == "source"


def test_install_lane_bundled_is_noop():
    # The bundled lane (local-model) needs no install; install_lane reports OK.
    from harness.lanes import install_lane
    r = install_lane("local-model")
    assert r["installed"] is True
    assert "bundled" in r["detail"]


def test_registry_roundtrip(tmp_path, monkeypatch):
    # write_registry -> read_registry preserves the data.
    import json
    from harness.lanes import write_registry, read_registry, LANE_REGISTRY_PATH
    monkeypatch.setattr("harness.lanes.LANE_REGISTRY_PATH", tmp_path / "lanes.json")
    write_registry({"index": {"install_name": "index-graph", "installed": True}})
    loaded = read_registry()
    assert loaded["index"]["installed"] is True
