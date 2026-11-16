"""fanout: every match runs or is recorded with its reason; the policy is enforced.

The tools here are small Python one-liners declared in manifests built for the
test, so nothing outside this repository runs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from plexus import policy  # noqa: E402
from plexus.manifest import Manifest  # noqa: E402
from plexus.runner.fanout import fanout, plan, verify  # noqa: E402

PY = sys.executable


def sense(organ, run, accepts=("image",), budget=(10, 512), network=False, writes=(), forms=("path",)):
    if run is not None:
        run = dict(run, forms=list(forms))
    return Manifest.from_dict({"organ": organ, "sense": {
        "schema": "plexus.sense/1", "tool": organ, "accepts": list(accepts), "run": run,
        "exact_call": "test", "verified": "test", "match_ext": [], "network": network,
        "budget": {"time_s": budget[0], "memory_mb": budget[1]}, "writes": list(writes)}})


def cli(code, *extra):
    return {"cli": [PY, "-c", code, "{item}", *extra]}


@pytest.fixture()
def png(tmp_path):
    p = tmp_path / "item.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    return p


def run(png, tmp_path, mans, **kw):
    return fanout(str(png), str(tmp_path / "out"), cfg={"roots": {}, "mcp_servers": {}},
                  manifests=mans, **kw)


def row(res, tool):
    return next(r for r in res["tools"] if r["tool"] == tool)


def test_every_match_is_a_row_with_status_time_and_error(png, tmp_path):
    mans = [sense("ok", cli("import sys; print(len(open(sys.argv[1],'rb').read()))")),
            sense("boom", cli("import sys; sys.exit('bad input: ' + sys.argv[1][-8:])")),
            sense("silent", cli("pass")),
            sense("plan-only", None),
            sense("audio-only", cli("pass"), accepts=("audio",))]
    res = run(png, tmp_path, mans)
    assert {r["tool"] for r in res["tools"]} == {"ok", "boom", "silent", "plan-only"}
    assert row(res, "ok")["status"] == "ok" and row(res, "ok")["seconds"] > 0
    out = Path(res["bundle"]).parent / row(res, "ok")["stdout"]
    assert out.read_text().strip() == "72"
    assert row(res, "boom")["status"] == "failed" and "bad input" in row(res, "boom")["error"]
    assert row(res, "silent")["status"] == "empty"
    assert row(res, "plan-only")["status"] == "not runnable"
    saved = json.loads(Path(res["bundle"]).read_text(encoding="utf-8"))
    assert saved["counts"] == {"empty": 1, "failed": 1, "not runnable": 1, "ok": 1}
    assert verify(res["bundle"])["verified"] is True


def test_time_budget_stops_a_slow_tool(png, tmp_path):
    res = run(png, tmp_path, [sense("slow", cli("import time; time.sleep(30)"), budget=(1, 512))])
    r = row(res, "slow")
    assert r["status"] == "timeout" and r["seconds"] < 15


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS does not enforce RLIMIT_AS")
def test_memory_budget_stops_a_hungry_tool(png, tmp_path):
    hog = "b = bytearray(600 * 1024 * 1024); print(len(b))"
    res = run(png, tmp_path, [sense("hog", cli(hog), budget=(30, 200))])
    r = row(res, "hog")
    assert r["status"] == "failed", r
    assert not (Path(res["bundle"]).parent / r["stdout"]).read_text().strip()


def test_a_tampered_output_fails_verification(png, tmp_path):
    res = run(png, tmp_path, [sense("ok", cli("print('x')"))])
    out = Path(res["bundle"]).parent / row(res, "ok")["stdout"]
    out.write_text("y\n")
    assert verify(res["bundle"])["verified"] is False


# ---- policy ---------------------------------------------------------------

def test_planted_manifest_that_exceeds_the_policy_is_refused_and_never_runs(png, tmp_path):
    canary = tmp_path / "ran.txt"
    touch = f"open(r'{canary}', 'w').write('ran')"
    planted = [
        sense("greedy-time", cli(touch), budget=(10_000, 512)),
        sense("greedy-memory", cli(touch), budget=(10, 64_000)),
        sense("net", cli(touch), network=True),
        sense("writer", cli(touch), writes=["/etc/plexus-was-here"]),
        sense("reacher", {"cli": [PY, "-c", touch, str(Path(__file__).resolve())]}),
    ]
    res = run(png, tmp_path, planted)
    reasons = {r["tool"]: r["reason"] for r in res["tools"]}
    assert all(r["status"] == "refused" for r in res["tools"]), res["tools"]
    assert "ceiling" in reasons["greedy-time"] and "ceiling" in reasons["greedy-memory"]
    assert "network" in reasons["net"]
    assert "writes outside its output folder" in reasons["writer"]
    assert "outside the item" in reasons["reacher"]
    assert not canary.exists()


def test_network_needs_both_the_manifest_and_the_grant(png, tmp_path):
    mans = [sense("net", cli("print(1)"), network=True)]
    assert row(run(png, tmp_path, mans), "net")["status"] == "refused"
    granted = run(png, tmp_path, mans, grants={"network": ["net"]})
    assert row(granted, "net")["status"] == "ok"


def test_refuse_list_and_kind_grants_come_from_the_policy_file(png, tmp_path):
    pol = policy.load()
    pol["refuse_tools"] = {"banned": "test reason"}
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({k: v for k, v in pol.items() if k != "sha256"}), encoding="utf-8")
    res = run(png, tmp_path, [sense("banned", cli("print(1)")), sense("eye", cli("print(1)"), accepts=("screen",))],
              policy_path=str(p), extra_kinds=["screen"])
    assert row(res, "banned")["reason"] == "refused by policy: test reason"
    assert "needs a grant" in row(res, "eye")["reason"]
    assert res["policy_sha256"] != policy.load()["sha256"]


def test_policy_file_with_an_unknown_kind_is_rejected(tmp_path):
    pol = {k: v for k, v in policy.load().items() if k != "sha256"}
    pol["kinds"]["allowed"].append("telepathy")
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(pol), encoding="utf-8")
    with pytest.raises(policy.PolicyError):
        policy.load(str(p))


def test_a_tool_that_takes_a_literal_is_not_applicable_to_a_path(png, tmp_path):
    res = plan(str(png), extra_kinds=["colour"], cfg={"roots": {}, "mcp_servers": {}},
               manifests=[sense("hex", cli("print(1)"), accepts=("colour",), forms=("literal",))])
    assert res["tools"][0]["status"] == "not applicable"


def test_a_missing_root_or_server_is_unavailable_not_dropped(png, tmp_path):
    mans = [sense("rooted", dict(cli("print(1)"), root="superframe")),
            sense("served", {"mcp": "nowhere", "tool": "t", "args": {}})]
    res = run(png, tmp_path, mans)
    assert {r["status"] for r in res["tools"]} == {"unavailable"}
