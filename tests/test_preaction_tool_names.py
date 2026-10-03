"""scope-escape/004: the side-effecting tool-name rule, shipped as an optional overlay.

Success criteria:
- the corpus file is the one frozen before the measurement (SHA-256 pinned), and
  the rule's regex equals the regex frozen in it;
- with the overlay on, all 8 named Orca side-effecting tools hold under
  scope-escape/004, and no look-alike read tool does;
- the measured counts are pinned: 27 of 48 side-effecting names held (recall
  0.5625, Wilson 95% [0.423, 0.693]) and 0 of 50 read-only names held (Wilson
  upper bound 0.071). The recall lower bound misses the 0.80 bar, which is why
  the rule ships off by default;
- false-success control: the shipped pack holds none of the 8 Orca names, so a
  suite that passes against the shipped pack alone fails here;
- off by default: the shipped pack carries no scope-escape/004 and its digest is
  unchanged by this module.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harness.preaction.contract import ALLOW, HOLD
from harness.preaction.core import MonitorConfig
from harness.preaction.optional_rules import (SIDE_EFFECT_TOOLS_RULE, optional_overlay,
                                              with_optional)
from harness.preaction.rules import evaluate, load_pack, pack_digest
from harness.uplift_bench import wilson_interval
from tests.preaction_fixtures import call, ctx, monitor

CORPUS_PATH = Path(__file__).with_name("fixtures") / "preaction_tool_names_v1.json"
CORPUS_SHA256 = "2d3d8ff36b179b30c7f588b141148227fbb59c4b661d14743fbda5ab48731ea1"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
SHIPPED = load_pack()
WITH_004 = load_pack(overlay=with_optional(None, "side-effect-tools"))


def _hits_004(pack, name: str) -> bool:
    return any(h.id == "scope-escape/004" for h in evaluate(pack, call(name), ctx()))


def _held(pack, name: str) -> bool:
    return any(h.action == HOLD for h in evaluate(pack, call(name), ctx()))


def test_corpus_is_the_frozen_one():
    digest = hashlib.sha256(CORPUS_PATH.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert digest == CORPUS_SHA256
    assert CORPUS["tool_regex"] == SIDE_EFFECT_TOOLS_RULE["match"]["tool_regex"]
    assert len(set(CORPUS["side_effecting"])) == 48
    assert len(set(CORPUS["read_only"])) == 50
    assert not set(CORPUS["side_effecting"]) & set(CORPUS["read_only"])


@pytest.mark.parametrize("name", CORPUS["orca_names"])
def test_overlay_holds_every_named_orca_tool(name):
    assert _hits_004(WITH_004, name)


@pytest.mark.parametrize("name", CORPUS["look_alikes_that_must_pass"])
def test_look_alikes_pass(name):
    assert not _hits_004(WITH_004, name)


def test_measured_counts_are_pinned():
    side = sum(_hits_004(WITH_004, n) for n in CORPUS["side_effecting"])
    false = sum(_hits_004(WITH_004, n) for n in CORPUS["read_only"])
    assert (side, false) == (27, 0)
    low, high = wilson_interval(side, 48)
    assert round(low, 3) == 0.423 and round(high, 3) == 0.693
    assert round(wilson_interval(false, 50)[1], 3) == 0.071
    assert low < CORPUS["bar"]["recall_lower_bound_min"]


def test_control_shipped_pack_holds_none_of_the_orca_names():
    assert sum(_held(SHIPPED, n) for n in CORPUS["orca_names"]) == 0


def test_off_by_default():
    assert "scope-escape/004" not in {r["id"] for r in SHIPPED["rules"]}
    assert pack_digest(load_pack()) == pack_digest(SHIPPED)
    assert MonitorConfig().rules_overlay is None


def test_with_optional_keeps_owner_hosts_and_adds_once():
    owner = {"allow_hosts": ["example.org"], "rules": []}
    merged = with_optional(with_optional(owner, "side-effect-tools"), "side-effect-tools")
    assert merged["allow_hosts"] == ["example.org"]
    assert [r["id"] for r in merged["rules"]] == ["scope-escape/004"]
    assert owner["rules"] == []


def test_unknown_overlay_name_is_refused():
    with pytest.raises(KeyError):
        optional_overlay("no-such-overlay")


def test_monitor_holds_through_the_full_path_only_when_switched_on(tmp_path):
    on = MonitorConfig(rules_overlay=with_optional(None, "side-effect-tools"))
    held = monitor(tmp_path / "on", config=on).assess(call("send_crypto_payment"), ctx())
    passed = monitor(tmp_path / "off").assess(call("send_crypto_payment"), ctx())
    assert held.verdict == HOLD
    assert passed.verdict == ALLOW


def test_owner_monitor_setting_switches_the_overlay_on():
    cfg = MonitorConfig.from_dict({"optional_rules": ["side-effect-tools"]})
    assert [r["id"] for r in cfg.rules_overlay["rules"]] == ["scope-escape/004"]
    assert cfg.digest() != MonitorConfig.from_dict({}).digest()
    with pytest.raises(KeyError):
        MonitorConfig.from_dict({"optional_rules": ["no-such-overlay"]})
    with pytest.raises(ValueError):
        MonitorConfig.from_dict({"optional_rules": "side-effect-tools"})
