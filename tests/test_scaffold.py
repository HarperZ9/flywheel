"""The per-message scaffold: organs that fire on EVERY turn as harness
guarantees, not tool calls the model remembers to make. The pre-pass
freezes every source the prompt names; the post-pass chains a turn
receipt and verifies any citations the answer carries. Failure degrades
honestly (named, never fabricated) and never blocks the answer."""

import hashlib

from harness.scaffold import scaffold_answer, scaffold_turn


def _fake_snapshotter(store):
    def snap(url):
        if url in store:
            return {"sha256": store[url], "url": url}
        raise ConnectionError("unreachable")
    return snap


def test_pre_pass_freezes_every_named_source():
    prompt = ("compare https://example.org/a and http://example.org/b "
              "please")
    env = scaffold_turn(prompt, snapshotter=_fake_snapshotter(
        {"https://example.org/a": "a" * 64, "http://example.org/b": "b" * 64}))
    assert env["schema"] == "flywheel.scaffold-envelope/v1"
    frozen = {s["url"]: s["sha256"] for s in env["sources_frozen"]}
    assert frozen == {"https://example.org/a": "a" * 64,
                      "http://example.org/b": "b" * 64}
    assert env["degraded"] == []
    assert env["prompt_sha256"] == hashlib.sha256(
        prompt.encode()).hexdigest()


def test_promptless_of_urls_is_clean_and_cheap():
    env = scaffold_turn("no sources here",
                        snapshotter=lambda u: (_ for _ in ()).throw(
                            AssertionError("must not be called")))
    assert env["sources_frozen"] == [] and env["degraded"] == []


def test_unreachable_source_degrades_honestly_never_fabricates():
    env = scaffold_turn("see https://dead.example.org/x",
                        snapshotter=_fake_snapshotter({}))
    assert env["sources_frozen"] == []
    assert len(env["degraded"]) == 1
    d = env["degraded"][0]
    assert d["url"] == "https://dead.example.org/x"
    assert "ConnectionError" in d["reason"]


def test_post_pass_chains_a_turn_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    env = scaffold_turn("hello", snapshotter=lambda u: None)
    r = scaffold_answer("the answer", env)
    assert r["schema"] == "flywheel.turn-receipt/v1"
    assert r["answer_sha256"] == hashlib.sha256(b"the answer").hexdigest()
    assert r["prompt_sha256"] == env["prompt_sha256"]
    assert r["chain_hash"], "the turn receipt must enter the audit chain"
    from harness.store import query_entities
    assert len(query_entities(kind="turn-receipt")) == 1


def test_post_pass_verifies_citations_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    src = b"the hubble constant is 73.17 km/s/Mpc"
    sha = hashlib.sha256(src).hexdigest()
    cite = {"source_sha256": sha, "start_byte": 23, "end_byte": 28,
            "quote_sha256": hashlib.sha256(src[23:28]).hexdigest()}
    env = scaffold_turn("q", snapshotter=lambda u: None)
    r = scaffold_answer("a", env, citations=[cite],
                        resolve=lambda h: src if h == sha else None)
    assert r["citations"]["all_verified"] is True
    r2 = scaffold_answer("a", env, citations=[cite], resolve=lambda h: None)
    assert r2["citations"]["all_verified"] is False
