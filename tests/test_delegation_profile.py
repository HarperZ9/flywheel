"""Unit tests for harness/delegation_profile.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.delegation_profile import (
    DEFAULT_PROFILE,
    DELEGATION_PROFILES,
    DELEGATION_SCHEMA,
    OUTBOUND_CHANNELS,
    evaluate_delegation,
    load_delegation_profile,
)


def _write_settings(home: Path, payload: object) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "settings.json").write_text(json.dumps(payload), encoding="utf-8")


def test_constants() -> None:
    assert DELEGATION_PROFILES == (
        "supervised",
        "workstation-native",
        "outbound-delegated",
    )
    assert DEFAULT_PROFILE == "supervised"
    assert OUTBOUND_CHANNELS == frozenset({"email", "social", "blog"})


def test_load_defaults_when_missing_or_invalid(tmp_path: Path) -> None:
    loaded = load_delegation_profile(tmp_path)
    assert loaded == {
        "schema": DELEGATION_SCHEMA,
        "profile": "supervised",
        "outbound_channels": {},
    }

    (tmp_path / "settings.json").write_text("{not valid json", encoding="utf-8")
    assert load_delegation_profile(tmp_path)["profile"] == "supervised"

    _write_settings(
        tmp_path,
        {
            "delegation_profile": "unknown-mode",
            "outbound_channels": {"email": True, "sms": True, "blog": "yes"},
        },
    )
    loaded = load_delegation_profile(tmp_path)
    assert loaded["profile"] == "supervised"
    assert loaded["outbound_channels"] == {"email": True}


def test_load_reads_valid_profile_and_channels(tmp_path: Path) -> None:
    _write_settings(
        tmp_path,
        {
            "delegation_profile": "outbound-delegated",
            "outbound_channels": {"email": True, "social": False, "blog": True},
        },
    )
    loaded = load_delegation_profile(tmp_path)
    assert loaded["profile"] == "outbound-delegated"
    assert loaded["outbound_channels"] == {
        "email": True,
        "social": False,
        "blog": True,
    }


def test_supervised_requires_prompt_and_receipt() -> None:
    res = evaluate_delegation("workspace.edit", "supervised")
    assert res["allowed_by_profile"] is False
    assert res["requires_per_action_prompt"] is True
    assert res["receipt_required"] is True
    assert res["profile"] == "supervised"


def test_workstation_native_allows_local_blocks_outbound() -> None:
    local = evaluate_delegation("agent.run", "workstation-native")
    assert local["allowed_by_profile"] is True
    assert local["requires_per_action_prompt"] is False
    assert local["receipt_required"] is True
    assert local["profile"] == "workstation-native"

    outbound = evaluate_delegation("outbound.send", "workstation-native", channel="email")
    assert outbound["allowed_by_profile"] is False
    assert outbound["requires_per_action_prompt"] is True
    assert outbound["receipt_required"] is True

    inferred = evaluate_delegation("email.send", "workstation-native")
    assert inferred["allowed_by_profile"] is False
    assert inferred["requires_per_action_prompt"] is True
    assert inferred["receipt_required"] is True


def test_outbound_delegated_requires_explicit_channel_opt_in(tmp_path: Path) -> None:
    _write_settings(
        tmp_path,
        {
            "delegation_profile": "outbound-delegated",
            "outbound_channels": {"email": True, "social": False},
        },
    )
    loaded = load_delegation_profile(tmp_path)

    email = evaluate_delegation("outbound.send", loaded, channel="email")
    assert email["allowed_by_profile"] is True
    assert email["requires_per_action_prompt"] is False
    assert email["receipt_required"] is True

    social = evaluate_delegation("outbound.post", loaded, channel="social")
    assert social["allowed_by_profile"] is False
    assert social["requires_per_action_prompt"] is True
    assert social["receipt_required"] is True

    blog = evaluate_delegation("blog.publish", loaded)
    assert blog["allowed_by_profile"] is False
    assert blog["requires_per_action_prompt"] is True
    assert blog["receipt_required"] is True

    unknown_chan = evaluate_delegation("outbound.send", loaded, channel="sms")
    assert unknown_chan["allowed_by_profile"] is False
    assert unknown_chan["requires_per_action_prompt"] is True
    assert unknown_chan["receipt_required"] is True

    bare = evaluate_delegation("outbound.send", "outbound-delegated", channel="email")
    assert bare["allowed_by_profile"] is False
    assert bare["requires_per_action_prompt"] is True
    assert bare["receipt_required"] is True


@pytest.mark.parametrize(
    "action",
    [
        "password_scrape",
        "credential_scrape",
        "scrape_cookies",
        "tos_bypass",
        "bypass_tos.login",
        "secret_exfil",
    ],
)
@pytest.mark.parametrize("profile_name", DELEGATION_PROFILES)
def test_tos_and_credential_scraping_always_blocked(
    action: str, profile_name: str
) -> None:
    cfg = {
        "profile": profile_name,
        "outbound_channels": {"email": True, "social": True, "blog": True},
    }
    res = evaluate_delegation(action, cfg, channel="email")
    assert res["allowed_by_profile"] is False
    assert res["requires_per_action_prompt"] is True
    assert res["receipt_required"] is True
    assert "ToS" in res["reason"] or "credential" in res["reason"]


def test_unknown_profile_and_empty_action_fail_closed() -> None:
    bad = evaluate_delegation("workspace.edit", "root-admin")
    assert bad["allowed_by_profile"] is False
    assert bad["requires_per_action_prompt"] is True
    assert bad["receipt_required"] is True
    assert bad["profile"] == "supervised"

    empty = evaluate_delegation("", "workstation-native")
    assert empty["allowed_by_profile"] is False
    assert empty["requires_per_action_prompt"] is True
    assert empty["receipt_required"] is True
