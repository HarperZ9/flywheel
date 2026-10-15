"""Falsifiers for parallel read-only subagents (the `tasks` tool)."""
import json
import threading
import time

from harness.code_session.agents import load_agents
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session


class Smart:
    """Parent asks for two children; each child answers after a pause."""
    name, model = "smart", "m"

    def __init__(self):
        self.active, self.peak, self.lock = 0, 0, threading.Lock()

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        first, last = messages[0]["content"], messages[-1]["content"]
        if first.startswith("child:"):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.4)
            with self.lock:
                self.active -= 1
            text = "answer for " + first.split(":", 1)[1].strip()
        elif "TOOL RESULTS" in last:
            text = "both done"
        else:
            text = 'TOOL tasks ' + json.dumps({"tasks": [
                {"agent": "explore", "prompt": "child: one"},
                {"agent": "explore", "prompt": "child: two"}]})
        return {"text": text, "model_ref": "smart:m", "seed": seed}


def test_two_read_only_children_run_at_the_same_time(tmp_path):
    backend = Smart()
    s = new_session(build_agent([backend]), str(tmp_path), mode="auto")
    s.set_agents(load_agents(str(tmp_path), None))
    started = time.time()
    r = s.turn("ask two questions")
    assert r.final == "both done"
    assert backend.peak == 2                                # they overlapped
    assert time.time() - started < 0.8 + 0.6                # not 2 x 0.4 s end to end plus slack
    result = [e.content for e in s.ledger.entries if e.kind == "tool_result"][0]
    assert result.index("answer for one") < result.index("answer for two")   # input order
    recs = [json.loads(e.content) for e in s.ledger.entries if e.kind == "subagent"]
    assert [r["index"] for r in recs] == [1, 2] and all(r["chain_ok"] for r in recs)


def test_a_writing_agent_is_refused_in_parallel(tmp_path):
    folder = tmp_path / ".flywheel" / "agents"
    folder.mkdir(parents=True)
    (folder / "w.md").write_text("---\nname: w\ntools: read_file, write_file\n---\nw",
                                 encoding="utf-8")
    s = new_session(build_agent([Smart()]), str(tmp_path), mode="auto")
    s.set_agents(load_agents(str(tmp_path), None))
    res = s.executor.execute("tasks", {"tasks": [{"agent": "w", "prompt": "x"}]})
    assert not res.ok and "read-only" in res.output


def test_limits_on_count_and_unknown_agents(tmp_path):
    s = new_session(build_agent([Smart()]), str(tmp_path), mode="auto")
    s.set_agents(load_agents(str(tmp_path), None))
    five = [{"agent": "explore", "prompt": "child: x"}] * 5
    assert not s.executor.execute("tasks", {"tasks": five}).ok
    assert not s.executor.execute("tasks", {"tasks": [{"agent": "nope", "prompt": "x"}]}).ok
