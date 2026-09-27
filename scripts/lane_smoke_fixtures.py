"""Test fixtures for the frozen lane smoke: one main action and one assertion per lane.

Each fixture writes its inputs under a throwaway folder, names the calls to make
(the last call is the lane's main tool from PLAN section 1a) and checks one fact
about the parsed reply. These are test fixtures for the smoke, not content that
ships in the app. A lane with no fixture here can reach ``health`` at most.

A fixture marked ``needs_model_server`` runs only when a model server answers
at one of the two fixed local addresses (``model_server_answering``); the smoke
records that fact, so a build machine running Ollama and a runner without one
get the same verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import socket
from typing import Callable

Call = tuple[str, dict]


MODEL_SERVER_ADDRESSES = (("127.0.0.1", 8765), ("127.0.0.1", 11434))


@dataclass(frozen=True)
class LaneFixture:
    calls: Callable[[Path, Path], list[Call]]  # (home, workdir) -> calls; last is main
    check: Callable[[object], bool]            # one assertion on the last reply's JSON
    needs_model_server: bool = False


def model_server_answering(addresses=MODEL_SERVER_ADDRESSES, timeout: float = 0.5) -> bool:
    """True when something accepts a connection at a fixed model server address."""
    for host, port in addresses:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _json(path: Path, value: object) -> Path:
    return _write(path, json.dumps(value, indent=2))


_BOUND = "binary search over a sorted array of 1024 elements does at most "
_THESIS = {"title": "Binary search comparison bounds", "disposition": "publishable",
           "claims": [
               {"text": _BOUND + "11 comparisons",
                "falsification": "a measured worst-case count above 11 for n=1024"},
               {"text": _BOUND + "3 comparisons",
                "falsification": "a measured worst-case count above 3 for n=1024"},
               {"text": "binary search is more elegant than linear search",
                "falsification": ""}]}
_MEASUREMENTS = {"measurements": [
    {"claim": _BOUND + "11 comparisons", "deviation": 0.0, "tolerance": 0.5,
     "method": "comparison-count", "evidence": ["floor(log2(1024)) + 1 = 11"]},
    {"claim": _BOUND + "3 comparisons", "deviation": 8.0, "tolerance": 0.5,
     "method": "comparison-count", "evidence": ["worst case 11, claimed 3"]}]}
_CORPUS = [
    {"kind": "comment", "id": f"c{i:02d}", "ref": "review", "text": text}
    for i, text in enumerate([
        "The battery life on this phone is incredible and lasts two days",
        "battery life is amazing, the best battery I have had",
        "the battery is terrible and drains so fast",
        "awful battery life, dead by lunch",
        "the display screen is gorgeous with bright colors",
        "stunning display, the screen colors pop",
        "the screen is too dim outdoors and the display glares",
        "the camera takes sharp photos in daylight",
        "camera photos are blurry at night",
        "the camera is fine for the price",
    ], start=1)]
_CANON_BLOCK = {
    "canon_schema": "canon.record/v1", "kind": "personality-block",
    "id": "smoke-block", "scope": "global",
    "data": {"title": "Smoke block", "body": "body text"},
    "provenance": {"harness": "author", "source_hash": "a" * 64, "native_id": None,
                   "session_id": None, "create_ord": 1, "create_time": None,
                   "model_slug": None},
    "temporal": {"valid_until": None, "supersedes": None},
}

def _gather(home: Path, work: Path) -> list[Call]:
    return [("gather.docs", {"path": str(_write(work / "note.md", "Lane smoke note.\n"))})]


def _gather_ok(reply: object) -> bool:
    rows = reply.get("catalog") if isinstance(reply, dict) else None
    return bool(rows) and all(str(row.get("sha256", "")) for row in rows)


def _crucible(home: Path, work: Path) -> list[Call]:
    return [("crucible.assess", {
        "thesis": str(_json(work / "thesis.json", _THESIS)),
        "measurements": str(_json(work / "measurements.json", _MEASUREMENTS))})]


def _crucible_ok(reply: object) -> bool:
    found = reply.get("assessment") if isinstance(reply, dict) else None
    counts = {key: found.get(key) for key in ("claims", "match", "drift", "unverifiable")
              } if isinstance(found, dict) else {}
    return counts == {"claims": 3, "match": 1, "drift": 1, "unverifiable": 1}


def _index(home: Path, work: Path) -> list[Call]:
    repo = work / "repo"
    _write(repo / "mod_a.py", "def alpha():\n    return 1\n")
    _write(repo / "mod_b.py", "from mod_a import alpha\n\n\ndef beta():\n    return alpha()\n")
    return [("index.symbol-definition", {"root": str(repo), "symbol": "alpha"})]


def _index_ok(reply: object) -> bool:
    rows = reply.get("definitions") if isinstance(reply, dict) else None
    return any(isinstance(row, dict) and row.get("file") == "mod_a.py"
               and row.get("line") == 1 for row in rows or [])


def _forum(home: Path, work: Path) -> list[Call]:
    return [("forum.route", {"text": "build the api database server endpoint"})]


def _forum_ok(reply: object) -> bool:
    return isinstance(reply, dict) and reply.get("decided") == "backend"


def _plexus(home: Path, work: Path) -> list[Call]:
    return [("plexus_route", {"source": "gather", "target": "crucible"})]


def _plexus_ok(reply: object) -> bool:
    return isinstance(reply, dict) and reply.get("connected") is True


def _mneme(home: Path, work: Path) -> list[Call]:
    turn = {"role": "user", "text": "The lane smoke keyword is cobaltwren."}
    return [("mneme.remember", {"session": "lane-smoke", "turns": [turn]}),
            ("mneme.recall", {"query": "cobaltwren", "strategy": "keyword"})]


def _mneme_ok(reply: object) -> bool:
    return (isinstance(reply, dict) and reply.get("schema") == "mneme.recall/1"
            and "cobaltwren" in json.dumps(reply.get("hits", [])))


def _canon(home: Path, work: Path) -> list[Call]:
    # Class B: the setup is a block in the lane's blocks folder. The smoke places
    # one where the app's default folder is, <home>/lanes/canon/blocks.
    _json(home / "lanes" / "canon" / "blocks" / "smoke-block.json", _CANON_BLOCK)
    return [("canon.validate", {})]


def _canon_ok(reply: object) -> bool:
    return (isinstance(reply, dict) and reply.get("target") == "blocks"
            and reply.get("ok") is True and reply.get("checked") == 1)


def _chorus(home: Path, work: Path) -> list[Call]:
    return [("chorus.run", {"corpus": str(_json(work / "corpus.json", _CORPUS)),
                            "verify": True})]


def _chorus_ok(reply: object) -> bool:
    return isinstance(reply, dict) and bool(reply.get("themes"))


def _relay(home: Path, work: Path) -> list[Call]:
    # Every widening argument is asked for; the engine's guard must drop or
    # force each one before the child sees it (the smoke routes the arguments
    # through lane_tier_gate.guard_args, as the app route does).
    return [("local_agent_run", {"goal": "Reply with the word ok.", "root": str(work),
                                 "max_steps": 1, "allow_write": True, "allow_exec": True,
                                 "online": True, "check": "whoami", "test_cmd": "whoami"})]


def _relay_ok(reply: object) -> bool:
    # Shape from relay ``run_projection`` (unchanged from 0.3.0 to 0.4.0): the binding says what the run
    # asked for and got. The launch grants nothing, so a reply that asked for
    # or got write, exec, online, a check or a test command fails here.
    binding = reply.get("request_binding") if isinstance(reply, dict) else None
    return (isinstance(binding, dict) and bool(reply.get("final_answer"))
            and binding.get("allow_write") is False and binding.get("allow_exec") is False
            and binding.get("granted_allow_write") is False
            and binding.get("granted_allow_exec") is False
            and binding.get("requested_root") is None and binding.get("online") is False
            and not binding.get("check_present") and not binding.get("test_cmd_present"))


def _surface(home: Path, work: Path) -> list[Call]:
    note = _write(work / "note.md", "# Smoke\n\nA perceived note.\n")
    return [("accountable-surface.perceive", {"subject": str(note)})]


def _surface_ok(reply: object) -> bool:
    if not isinstance(reply, dict):
        return False
    data, provenance = reply.get("data"), reply.get("provenance")
    return (isinstance(data, dict) and isinstance(provenance, dict)
            and str(provenance.get("digest", "")).startswith("sha256:")
            and provenance["digest"] == "sha256:" + str(data.get("identity_sha256")))



def _articulate(home: Path, work: Path) -> list[Call]:
    return [("score", {"text": "The gateway starts each lane as a child process."})]


def _articulate_ok(reply: object) -> bool:
    keys = ("texture_score", "hard_hits", "advisories")
    return isinstance(reply, dict) and all(isinstance(reply.get(k), int) for k in keys)


def _calibrate(home: Path, work: Path) -> list[Call]:
    return [("calibrate-pro.list-panels", {})]


def _calibrate_ok(reply: object) -> bool:
    # The v2.0.0 catalog slice holds 58 panels (PLAN section 1b).
    panels = reply.get("panels") if isinstance(reply, dict) else None
    return isinstance(panels, list) and reply.get("count") == len(panels) == 58


_OBJECTIVE = "state the worst-case comparison count"


def _learn(home: Path, work: Path) -> list[Call]:
    return [("learn_tutor_plan", {"sessionId": "lane-smoke", "topic": "binary search",
                                  "objectives": [_OBJECTIVE]})]


def _learn_ok(reply: object) -> bool:
    return (isinstance(reply, dict) and reply.get("sessionId") == "lane-smoke"
            and reply.get("objectives") == [_OBJECTIVE])


def _telos(home: Path, work: Path) -> list[Call]:
    return [("telos.catalog", {})]


def _telos_ok(reply: object) -> bool:
    if not isinstance(reply, dict):
        return False
    tools = reply.get("tools")
    return (reply.get("schema") == "project-telos.mcp-tool-catalog/v1"
            and isinstance(tools, list) and len(tools) > 0)


# Lanes the smoke launches with no main fixture, and why. Each stays at the
# health level here; its main action is measured elsewhere.
NO_FIXTURE = {
    "local-model": "local_agent_run needs a model server at a fixed address "
                   "(127.0.0.1:8765 or Ollama); the installed-app acceptance runs it "
                   "against a stub, and a smoke on a machine with a model would "
                   "measure that machine",
    "writing": "writing.diagnose reads a recorded revision (project, section and "
               "revision records first), which a one-call fixture cannot build",
}

FIXTURES: dict[str, LaneFixture] = {
    "gather": LaneFixture(_gather, _gather_ok),
    "crucible": LaneFixture(_crucible, _crucible_ok),
    "index": LaneFixture(_index, _index_ok),
    "forum": LaneFixture(_forum, _forum_ok),
    "plexus": LaneFixture(_plexus, _plexus_ok),
    "mneme": LaneFixture(_mneme, _mneme_ok),
    "canon": LaneFixture(_canon, _canon_ok),
    "chorus": LaneFixture(_chorus, _chorus_ok),
    "relay": LaneFixture(_relay, _relay_ok, needs_model_server=True),
    "accountable-surface": LaneFixture(_surface, _surface_ok),
    "articulate": LaneFixture(_articulate, _articulate_ok),
    "calibrate-pro": LaneFixture(_calibrate, _calibrate_ok),
    "learn": LaneFixture(_learn, _learn_ok),
    "telos": LaneFixture(_telos, _telos_ok),
}
