"""Falsifiers for compaction, @-mentions and /context in `flywheel code`."""
import hashlib
import json

from harness.code_session import slash
from harness.code_session.backends import build_agent
from harness.code_session.context import _alternate, estimate
from harness.code_session.session import new_session
from tests.test_code_session import ScriptBackend, _bare_runner


def _session(tmp_path, replies, budget):
    backend = ScriptBackend(replies)
    s = new_session(build_agent([backend]), str(tmp_path), mode="auto", runner=_bare_runner)
    s.compact_budget = budget
    return s, backend


def test_a_long_conversation_is_folded_and_still_alternates(tmp_path):
    s, backend = _session(tmp_path, [f"answer {i} " + "word " * 400 for i in range(14)],
                          budget=2000)
    for i in range(14):
        s.turn(f"question {i} " + "detail " * 300)
    assert any(e.kind == "compaction" for e in s.ledger.entries)
    sent = backend.seen[-1]
    roles = [m["role"] for m in sent]
    assert all(a != b for a, b in zip(roles, roles[1:])), roles
    assert set(roles) <= {"user", "assistant"}
    assert all(set(m) == {"role", "content"} for m in sent)
    assert "question 0" in sent[0]["content"]          # the first request stays verbatim
    unfolded = sum(len(e.content) for e in s.ledger.entries if e.kind in ("user", "assistant"))
    assert estimate("", sent) * 4 < unfolded              # the model saw less than the record holds
    assert s.ledger.verify()


def test_budget_zero_never_folds(tmp_path):
    s, _ = _session(tmp_path, ["a " * 500] * 12, budget=0)
    for i in range(12):
        s.turn("q " * 500)
    assert not any(e.kind == "compaction" for e in s.ledger.entries)


def test_alternate_merges_neighbours_and_drops_extra_keys():
    out = _alternate([{"role": "user", "content": "a"}, {"role": "system", "content": "b",
                      "compaction_summary": True}, {"role": "assistant", "content": "c"}])
    assert out == [{"role": "user", "content": "a\n\nb"}, {"role": "assistant", "content": "c"}]


def test_mentions_attach_files_inside_the_folder_only(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_bytes(b"print('hi')\n")
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("TOPSECRETVALUE", encoding="utf-8")
    s, backend = _session(tmp_path, ["ok"], budget=0)
    s.turn("look at @src/a.py and @../outside-secret.txt please")
    sent = backend.seen[-1][-1]["content"]
    assert "--- FILE: src/a.py ---\nprint('hi')" in sent and "TOPSECRETVALUE" not in sent
    rec = [json.loads(e.content) for e in s.ledger.entries if e.kind == "mention"][0]
    assert rec == [{"path": "src/a.py", "truncated": False,
                    "sha256": hashlib.sha256(b"print('hi')\n").hexdigest()}]


def test_an_email_address_is_not_a_mention(tmp_path):
    s, backend = _session(tmp_path, ["ok"], budget=0)
    s.turn("mail me at someone@example.org")
    assert not any(e.kind == "mention" for e in s.ledger.entries)


def test_context_and_compact_commands(tmp_path):
    s, _ = _session(tmp_path, ["r " * 50] * 12, budget=0)
    assert "estimated" in slash.dispatch(s, "/context")
    assert "nothing to fold" in slash.dispatch(s, "/compact")
    for i in range(12):
        s.turn("q " * 50)
    assert slash.dispatch(s, "/compact").startswith("folded")
    assert "1 fold(s)" in slash.dispatch(s, "/context")
