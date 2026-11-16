"""pick, kinds and senses on the read-only MCP server; fanout only on `plexus mcp --run`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from plexus.cli import main  # noqa: E402
from plexus.mcp import handle  # noqa: E402
from plexus.runner.mcp_run import handle_run  # noqa: E402


def call(h, name, args):
    r = h({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": name, "arguments": args}})
    res = r["result"]
    assert not res.get("isError"), res
    return json.loads(res["content"][0]["text"])


def names(h):
    return {t["name"] for t in h({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]}


def test_read_only_server_lists_pick_kinds_senses_and_not_fanout():
    have = names(handle)
    assert {"plexus_pick", "plexus_kinds", "plexus_senses"} <= have
    assert "plexus_fanout" not in have


def test_run_server_adds_fanout_and_marks_it_as_starting_programs():
    tools = handle_run({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
    fan = next(t for t in tools if t["name"] == "plexus_fanout")
    assert fan["annotations"]["readOnlyHint"] is False and fan["annotations"]["openWorldHint"] is False
    assert names(handle) < {t["name"] for t in tools}


def test_pick_over_mcp_picks_or_abstains():
    assert call(handle, "plexus_pick", {"request": "compose a symphony"})["abstained"] is True
    hit = call(handle, "plexus_pick", {"request": "measure the colours and symmetry of an image",
                                        "senses": True, "threshold": 0.0})
    assert hit["picked"] == "design_parts.measure_all"


def test_kinds_and_senses_over_mcp():
    assert call(handle, "plexus_kinds", {"item": "#b46f00"})["kinds"] == ["colour"]
    got = call(handle, "plexus_senses", {"item": "#b46f00"})
    assert "build_color.info" in {t["tool"] for t in got["tools"]}
    assert call(handle, "plexus_kinds", {"item": ""})["unknown"] is True


def test_fanout_dry_run_over_mcp_plans_without_running(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    got = call(handle_run, "plexus_fanout", {"item": str(p), "dry_run": True, "out": str(tmp_path)})
    assert got["kinds"][:2] == ["file", "image"] and got["bundle"] == ""
    assert all(r["status"] != "ok" for r in got["tools"])
    assert not list(tmp_path.glob("x.png-*"))


def test_cli_pick_is_installed_and_senses_check_passes(capsys):
    assert main(["pick", "recall my stored notes", "--builtin"]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == "plexus.pick/1"
    assert main(["senses", "--check"]) == 0
    assert json.loads(capsys.readouterr().out)["in_step"] is True
