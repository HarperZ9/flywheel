from agent_routing_kit import estimate_context, route_task


def test_routes_public_capability_by_default():
    result = route_task("write docs and tests for a Python CLI package")

    names = [capability.name for capability, _score in result.matches]

    assert "python-packaging" in names
    assert "documentation" in names
    assert "restricted-operation" not in names


def test_private_lanes_are_opt_in():
    default = route_task("review private broker credential live payload corridor")
    included = route_task(
        "review private broker credential live payload corridor",
        include_private=True,
    )

    assert all(capability.risk == "public" for capability, _score in default.matches)
    assert any(capability.risk != "public" for capability, _score in included.matches)
    assert default.excluded_risk_counts == {"private": 1, "restricted": 1}
    assert included.excluded_risk_counts == {}


def test_default_markdown_reports_omitted_private_matches():
    result = route_task("review private broker credential live payload corridor")
    markdown = result.to_markdown()

    assert "Private/restricted matches omitted by default" in markdown
    assert "private=1" in markdown
    assert "restricted=1" in markdown


def test_default_json_reports_omitted_private_counts():
    result = route_task("review private broker credential live payload corridor")
    payload = result.to_dict()

    assert payload["excluded_risk_counts"] == {"private": 1, "restricted": 1}


def test_context_budget_statuses():
    assert estimate_context("short", max_tokens=100).status == "fits"
    assert estimate_context("x" * 320, max_tokens=100).status == "warn"
    assert estimate_context("x" * 500, max_tokens=100).status == "over"
