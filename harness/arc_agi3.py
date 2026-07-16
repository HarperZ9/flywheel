"""arc_agi3.py — the ARC-AGI-3 agents-API lane, zero-dep and gated.

A thin client for the ARC Prize agents API (three.arcprize.org: scorecard
open/close, game reset, ACTION1..7) plus `play`, which drives one game with
an injectable policy and records the run as an events.jsonl trace in the
SAME shape schema_trace_intake admits — a flywheel-driven run is graded by
the identical zero-trust loop as any external release.

Honesty gates: no API key is a NAMED refusal (never a silent anonymous
call); the trace's level_up is derived from observed score increments (an
interpretation of the frame contract, stated here so it is not overread);
a run that exhausts its action budget records STOPPED, never WIN. Nothing
fires on its own — live play needs the operator's key in ARC_API_KEY.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

BASE_URL = "https://three.arcprize.org"
_COORD_ACTION = 6
_TIMEOUT = 60


class ArcError(RuntimeError):
    """A refused or failed API interaction, named."""


def _default_transport(method: str, path: str, payload, *, api_key: str,
                       base_url: str):
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        method=method)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.status, json.loads(resp.read().decode() or "{}")


class ArcClient:
    """The agents API, threaded: one scorecard, one guid per session."""

    def __init__(self, api_key: "str | None" = None, base_url: str = BASE_URL,
                 transport=None, env: "dict | None" = None):
        env = os.environ if env is None else env
        self.api_key = api_key or env.get("ARC_API_KEY", "")
        self.base_url = base_url
        self._transport = transport

    def _call(self, method: str, path: str, payload=None):
        if not self.api_key:
            raise ArcError("no ARC_API_KEY present; live play is gated on "
                           "the operator's key (https://docs.arcprize.org)")
        if self._transport is not None:
            code, body = self._transport(method, path, payload)
        else:
            code, body = _default_transport(method, path, payload,
                                            api_key=self.api_key,
                                            base_url=self.base_url)
        if code != 200:
            raise ArcError(f"{method} {path} returned {code}: "
                           f"{str(body)[:200]}")
        return body

    def games(self) -> list:
        return self._call("GET", "/api/games")

    def open_scorecard(self) -> str:
        return self._call("POST", "/api/scorecard/open", {})["card_id"]

    def close_scorecard(self, card_id: str) -> dict:
        return self._call("POST", "/api/scorecard/close",
                          {"card_id": card_id})

    def reset(self, game_id: str, card_id: str,
              guid: "str | None" = None) -> dict:
        payload = {"game_id": game_id, "card_id": card_id}
        if guid:
            payload["guid"] = guid
        return self._call("POST", "/api/cmd/RESET", payload)

    def act(self, action: int, game_id: str, guid: str,
            x: "int | None" = None, y: "int | None" = None,
            reasoning: "str | None" = None) -> dict:
        if action == _COORD_ACTION:
            if x is None or y is None:
                raise ArcError("ACTION6 requires x and y")
        elif x is not None or y is not None:
            raise ArcError(f"ACTION{action} takes no coordinates")
        payload = {"game_id": game_id, "guid": guid}
        if x is not None:
            payload.update(x=x, y=y)
        if reasoning:
            payload["reasoning"] = reasoning
        return self._call("POST", f"/api/game/action/{action}", payload)


def play(client: ArcClient, game_id: str, *, policy, max_actions: int = 3000,
         trace_dir: "str | Path | None" = None, card_id: "str | None" = None) -> dict:
    """Drive one game: `policy(frame) -> (action, x, y)` chooses each move.
    Records run.json + events.jsonl in the schema-intake-admissible shape.
    Returns {state, actions, score, win_score, guid}."""
    own_card = card_id is None
    card = card_id or client.open_scorecard()
    frame = client.reset(game_id, card)
    guid = frame.get("guid", "")
    events: list = []
    started = time.time()
    events.append({"kind": "run_started", "seq": 1, "ts": started,
                   "game_id": game_id, "provider": "flywheel",
                   "model": "policy", "max_actions": max_actions,
                   "win_levels": 0, "workdir": "", "resumed": False,
                   "resumed_transitions": 0})
    score = int(frame.get("score", 0))
    state = str(frame.get("state", "NOT_FINISHED")).upper()
    steps = 0
    while state not in ("WIN", "GAME_OVER") and steps < max_actions:
        action, x, y = policy(frame)
        frame = client.act(action, game_id, guid, x=x, y=y)
        new_score = int(frame.get("score", score))
        state = str(frame.get("state", "NOT_FINISHED")).upper()
        events.append({"kind": "action_taken", "seq": len(events) + 1,
                       "ts": time.time(), "step_index": steps,
                       "action": action, "state": state,
                       # level_up = an observed score increment; the honest
                       # reading of the frame contract, stated in the module
                       "level_up": new_score > score})
        score = new_score
        steps += 1
    final = "WIN" if state == "WIN" else "STOPPED"
    events.append({"kind": "run_finished", "seq": len(events) + 1,
                   "ts": time.time(), "state": final, "actions": steps})
    if trace_dir is not None:
        d = Path(trace_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events), encoding="utf-8")
        (d / "run.json").write_text(json.dumps(
            {"game_id": game_id, "provider": "flywheel", "model": "policy",
             "max_actions": max_actions, "win_levels": score,
             "workdir": "", "started_at": started}), encoding="utf-8")
    if own_card:
        client.close_scorecard(card)
    return {"state": final, "actions": steps, "score": score,
            "win_score": frame.get("win_score"), "guid": guid}
