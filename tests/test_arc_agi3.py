"""The ARC-AGI-3 lane must be honest by construction: no key -> a named
refusal (never a silent anonymous call), the client threads card/guid
state exactly as the API defines, and a played run writes the SAME
events.jsonl trace shape the schema intake admits — our own runs are
graded by the identical zero-trust loop as anyone else's."""

import json

import pytest

from harness.arc_agi3 import ArcClient, ArcError, play
from harness.schema_trace_intake import rhae, stream_summary


class _FakeTransport:
    """Scripted API: a 2-level game where any action advances one step and
    every 3rd step clears a level (score increments)."""

    def __init__(self):
        self.calls = []
        self.steps = 0
        self.score = 0

    def __call__(self, method, path, payload):
        self.calls.append((method, path, dict(payload or {})))
        if path == "/api/games":
            return 200, [{"game_id": "zz99-test", "title": "ZZ99"}]
        if path == "/api/scorecard/open":
            return 200, {"card_id": "card-1"}
        if path == "/api/scorecard/close":
            return 200, {"card_id": "card-1", "won": 1}
        if path == "/api/cmd/RESET" or path.endswith("/game/reset"):
            self.steps, self.score = 0, 0
            return 200, {"guid": "g-1", "state": "NOT_FINISHED",
                         "score": 0, "win_score": 2, "frame": [[0]]}
        if "/game/action/" in path:
            self.steps += 1
            if self.steps % 3 == 0:
                self.score += 1
            state = "WIN" if self.score >= 2 else "NOT_FINISHED"
            return 200, {"guid": payload["guid"], "state": state,
                         "score": self.score, "win_score": 2,
                         "frame": [[self.steps]]}
        return 404, {"error": f"unknown path {path}"}


def test_missing_key_is_a_named_refusal():
    with pytest.raises(ArcError) as err:
        ArcClient(api_key=None, transport=_FakeTransport(),
                  env={}).games()
    assert "ARC_API_KEY" in str(err.value)


def test_client_threads_card_and_guid_through_the_session():
    t = _FakeTransport()
    c = ArcClient(api_key="k", transport=t)
    assert c.games()[0]["game_id"] == "zz99-test"
    card = c.open_scorecard()
    assert card == "card-1"
    frame = c.reset("zz99-test", card)
    assert frame["guid"] == "g-1"
    out = c.act(1, "zz99-test", frame["guid"])
    assert out["score"] == 0
    # action 6 carries coordinates; others must refuse them
    c.act(6, "zz99-test", "g-1", x=3, y=4)
    sent = t.calls[-1][2]
    assert sent["x"] == 3 and sent["y"] == 4
    with pytest.raises(ArcError):
        c.act(2, "zz99-test", "g-1", x=1, y=1)
    assert c.close_scorecard(card)["won"] == 1


def test_play_writes_an_intake_admissible_trace(tmp_path):
    t = _FakeTransport()
    c = ArcClient(api_key="k", transport=t)
    result = play(c, "zz99-test", policy=lambda frame: (1, None, None),
                  max_actions=10, trace_dir=tmp_path)
    assert result["state"] == "WIN"
    assert result["actions"] == 6            # two levels, 3 steps each
    # the trace is admissible by OUR OWN zero-trust intake
    summary = stream_summary(tmp_path / "events.jsonl")
    assert summary["state"] == "WIN"
    assert summary["completed"] == [3, 3]
    per_level, game = rhae([3, 3], summary["completed"])
    assert game == 100.0
    run = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert run["game_id"] == "zz99-test"
    assert run["provider"] == "flywheel"


def test_play_stops_honestly_at_the_action_budget(tmp_path):
    t = _FakeTransport()
    c = ArcClient(api_key="k", transport=t)
    result = play(c, "zz99-test", policy=lambda frame: (1, None, None),
                  max_actions=4, trace_dir=tmp_path)
    assert result["state"] == "STOPPED"      # budget hit before WIN
    summary = stream_summary(tmp_path / "events.jsonl")
    assert summary["state"] == "STOPPED"
    assert summary["completed"] == [3]       # one level cleared
    assert summary["incomplete_actions"] == 1
