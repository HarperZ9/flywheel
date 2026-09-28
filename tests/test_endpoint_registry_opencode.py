"""OpenCode route-construction regression for endpoint_registry."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.endpoint_registry import make_endpoint_proposer


def test_opencode_roster_name_routes_to_plan_backend_without_construction_chat(monkeypatch):
    from harness import endpoints
    events = []

    class OpenCodePlanBackend:
        name = "opencode-plan"

        def chat(self, messages, *, system, max_tokens, temperature, seed):
            events.append(("chat", messages, system, max_tokens, temperature, seed))
            return {"text": "opencode routed", "model_ref": "opencode-plan:dummy", "seed": seed}

    def fake_build_endpoints(*, only_configured=True):
        events.append(("build", only_configured))
        return [OpenCodePlanBackend()]

    monkeypatch.setattr(endpoints, "build_endpoints", fake_build_endpoints)
    proposer = make_endpoint_proposer("opencode", extract=False)
    assert proposer.backend.name == "opencode-plan"
    assert [event for event in events if event[0] == "chat"] == []

    out = proposer.generate("route me", seed=11, temperature=0.0, max_new_tokens=9,
                            system="system text")

    assert out.text == "opencode routed"
    assert out.model_ref == "opencode-plan:dummy"
    assert out.seed == 11
    assert events == [
        ("build", False),
        ("chat", [{"role": "user", "content": "route me"}], "system text", 9, 0.0, 11),
    ]