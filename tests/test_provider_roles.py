from harness.provider_roles import (
    annotate_provider_roles,
    provider_alias_map,
    provider_role,
    provider_roles_for,
)


def test_provider_role_normalizes_known_harness_aliases():
    assert provider_role("serve") == "flywheel"
    assert provider_role("gpt-5.3-codex-spark") == "codex"
    assert provider_role("5.3-Codex-Spark") == "codex"
    assert provider_role("open-code") == "opencode"
    assert provider_role("ollama") == "ollama_local"
    assert provider_role("claude-code") == "claude_code"
    assert provider_role("dry") == "dry_fixture"


def test_provider_roles_for_preserves_order_and_deduplicates_roles():
    roles = provider_roles_for(["serve", "flywheel", "codex", "open-code", "opencode"])

    assert roles == ["flywheel", "codex", "opencode"]


def test_annotate_provider_roles_preserves_raw_provider_and_adds_canonical_role():
    rows = [
        {"provider": "serve"},
        {"provider": "open-code"},
        {"provider": "unknown-provider"},
    ]

    assert annotate_provider_roles(rows) is rows
    assert rows[0]["provider"] == "serve"
    assert rows[0]["provider_role"] == "flywheel"
    assert rows[1]["provider_role"] == "opencode"
    assert rows[2]["provider_role"] == "unknown-provider"
    assert provider_alias_map()["gpt-5.3-codex-spark"] == "codex"


def test_annotate_derives_from_provider_and_flags_a_false_role_claim():
    # a row whose self-declared provider_role disagrees with its actual
    # provider is laundering: annotate must keep the provider-derived role
    # (the ground truth) and NAME the conflict, never adopt the claim.
    rows = [{"provider": "ollama", "provider_role": "flywheel"}]
    annotate_provider_roles(rows)
    assert rows[0]["provider_role"] == "ollama_local"  # from the provider, not the claim
    assert rows[0]["role_conflict"] == {"claimed": "flywheel", "derived": "ollama_local"}


def test_annotate_no_conflict_when_claim_matches_provider():
    rows = [{"provider": "serve", "provider_role": "flywheel"}]
    annotate_provider_roles(rows)
    assert rows[0]["provider_role"] == "flywheel"
    assert "role_conflict" not in rows[0]


def test_annotate_leaves_a_claim_only_row_untouched():
    # no provider to check against: the claim stands (nothing verified it),
    # normalized through the alias map like before
    rows = [{"provider_role": "codex_harness"}]
    annotate_provider_roles(rows)
    assert rows[0]["provider_role"] == "codex_harness"
    assert "role_conflict" not in rows[0]
