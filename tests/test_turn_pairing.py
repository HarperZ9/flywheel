"""7.2, F-03: an answer is paired with the prompt it answers: by prompt_id
(Claude Code), by turn_id (Codex), else first-in-first-out per session; an
unanswered prompt becomes an unpaired turn after its time to live, checked
lazily; a continued Stop adds a segment; a Stop with no prompt is unpaired and
never pretends the prompt was empty."""
import hashlib
import os

from harness.capture_hooks.protocol import commitment
from turn_fixtures import SESSION, Clock, custody_bytes, receipts, turn_store


def _prompt(store, text, key=None, client="claude-code", session=SESSION):
    salt = os.urandom(32)
    store.prompt(client, session, key, commitment=commitment("prompt", salt, text), salt=salt)
    return commitment("prompt", salt, text)


def _stop(store, text, key=None, client="claude-code", session=SESSION, active=False):
    salt = os.urandom(32)
    return store.stop(client, session, key, commitment=commitment("answer", salt, text),
                      salt=salt, stop_hook_active=active)


def test_pairing_by_prompt_id(tmp_path):
    with turn_store(tmp_path) as store:
        _prompt(store, "first", "pid-1")
        second = _prompt(store, "second", "pid-2")
        result = _stop(store, "answer to second", "pid-2")
    assert result["pairing"] == "prompt_id"
    assert receipts(tmp_path)[-1]["data"]["prompt_commitment"] == second


def test_pairing_by_turn_id_for_codex(tmp_path):
    with turn_store(tmp_path) as store:
        first = _prompt(store, "codex prompt", "turn-7", client="codex")
        result = _stop(store, "codex answer", "turn-7", client="codex")
    assert result["pairing"] == "turn_id"
    assert receipts(tmp_path)[-1]["data"]["prompt_commitment"] == first


def test_first_in_first_out_without_keys(tmp_path):
    with turn_store(tmp_path) as store:
        a = _prompt(store, "prompt a")
        b = _prompt(store, "prompt b")
        _stop(store, "answer a")
        _stop(store, "answer b")
    data = [r["data"] for r in receipts(tmp_path)]
    assert [d["prompt_commitment"] for d in data] == [a, b]
    assert {d["pairing"] for d in data} == {"fifo"}


def test_an_unanswered_prompt_becomes_unpaired_after_its_ttl_lazily(tmp_path):
    clock = Clock()
    with turn_store(tmp_path, clock=clock) as store:
        waiting = _prompt(store, "never answered", "pid-1")
        clock.now += 23 * 3600
        assert store.expire() == 0
        clock.now += 2 * 3600
        _stop(store, "other session answer", "pid-x", session="1" * 8 + "-2222-3333-4444-" + "5" * 12)
    unpaired = [r["data"] for r in receipts(tmp_path) if r["data"]["pairing"] == "unpaired"]
    assert any(d["prompt_commitment"] == waiting and d["answer_commitment"] is None
               for d in unpaired)


def test_a_continued_stop_adds_a_segment_to_the_same_prompt(tmp_path):
    with turn_store(tmp_path) as store:
        prompt = _prompt(store, "long task", "pid-1")
        first = _stop(store, "part one", "pid-1")
        second = _stop(store, "part two", "pid-1", active=True)
    assert (first["segment"], second["segment"]) == (0, 1)
    data = [r["data"] for r in receipts(tmp_path)]
    assert [d["prompt_commitment"] for d in data] == [prompt, prompt]


def test_a_stop_with_no_prompt_is_unpaired_and_no_empty_digest_is_written(tmp_path):
    with turn_store(tmp_path) as store:
        result = _stop(store, "answer from nowhere", "pid-9")
    assert result["pairing"] == "unpaired"
    data = receipts(tmp_path)[-1]["data"]
    assert data["prompt_commitment"] is None
    empty = hashlib.sha256(b"").hexdigest()
    assert empty.encode() not in custody_bytes(tmp_path)
    assert empty[:12].encode() not in custody_bytes(tmp_path)
