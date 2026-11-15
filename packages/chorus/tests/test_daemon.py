import json

from chorus.daemon import Watchlist, DigestStore, tick


def _rows(ref, n):
    return [{"kind": "comment", "id": f"c{i}", "ref": ref, "text": f"great sound design {i % 3}",
             "meta": {"author": "a", "like_count": i}} for i in range(n)]


def _corpus(tmp_path, name, ref, n):
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(_rows(ref, n)), encoding="utf-8")
    return str(p)


class _Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        self.t += 1.0
        return self.t


def test_first_tick_synthesizes_stores_and_advances_the_cursor(tmp_path):
    corpus = _corpus(tmp_path, "a", "vidA", 6)
    store = DigestStore(str(tmp_path / "store"))
    wl = Watchlist([corpus])
    out = tick(wl, store, clock=_Clock())
    assert out["ticked"] == 1
    assert out["results"][0]["status"] == "synthesized"
    assert store.cursor(corpus) is not None
    assert len(store.recent(10)) == 1


def test_unchanged_corpus_is_a_no_op_on_re_tick(tmp_path):
    corpus = _corpus(tmp_path, "a", "vidA", 6)
    store = DigestStore(str(tmp_path / "store"))
    wl = Watchlist([corpus])
    tick(wl, store, clock=_Clock())
    out = tick(wl, store, clock=_Clock())
    assert out["results"][0]["status"] == "unchanged"
    assert len(store.recent(10)) == 1        # no second digest written


def test_a_grown_corpus_is_re_synthesized(tmp_path):
    corpus = _corpus(tmp_path, "a", "vidA", 6)
    store = DigestStore(str(tmp_path / "store"))
    wl = Watchlist([corpus])
    tick(wl, store, clock=_Clock())
    # the corpus grows: new comments arrive
    (tmp_path / "a.json").write_text(json.dumps(_rows("vidA", 9)), encoding="utf-8")
    out = tick(wl, store, clock=_Clock())
    assert out["results"][0]["status"] == "synthesized"
    assert len(store.recent(10)) == 2


def test_a_bad_corpus_is_named_and_does_not_advance_the_cursor(tmp_path):
    store = DigestStore(str(tmp_path / "store"))
    wl = Watchlist([str(tmp_path / "nope.json")])
    out = tick(wl, store, clock=_Clock())
    assert out["results"][0]["status"] == "error"
    assert store.cursor(str(tmp_path / "nope.json")) is None
    assert store.recent(10) == []


def test_watchlist_add_list_remove_roundtrips(tmp_path):
    wl_path = str(tmp_path / "watch.json")
    wl = Watchlist([])
    wl.add("corpus-1")
    wl.add("corpus-1")               # idempotent
    wl.add("corpus-2")
    wl.save(wl_path)
    reloaded = Watchlist.load(wl_path)
    assert reloaded.sources == ["corpus-1", "corpus-2"]
    reloaded.remove("corpus-1")
    assert reloaded.sources == ["corpus-2"]


def test_recent_returns_newest_first_with_summary_fields(tmp_path):
    store = DigestStore(str(tmp_path / "store"))
    wl = Watchlist([_corpus(tmp_path, "a", "vidA", 6), _corpus(tmp_path, "b", "vidB", 4)])
    tick(wl, store, clock=_Clock())
    recent = store.recent(10)
    assert len(recent) == 2
    r = recent[0]
    assert {"at", "corpus", "responds_to", "n_items", "verified", "digest_sha256"} <= set(r)


def test_cli_watch_then_daemon_once_synthesizes(tmp_path, capsys):
    from chorus.cli import main
    corpus = _corpus(tmp_path, "a", "vidA", 6)
    wl = str(tmp_path / "watch.json")
    store = str(tmp_path / "store")
    assert main(["watch", "add", corpus, "--watchlist", wl]) == 0
    capsys.readouterr()
    assert main(["daemon", "--once", "--watchlist", wl, "--store", store]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ticked"] == 1 and out["results"][0]["status"] == "synthesized"


def test_cli_digests_lists_recent_from_the_store(tmp_path, capsys):
    from chorus.cli import main
    corpus = _corpus(tmp_path, "a", "vidA", 6)
    wl = str(tmp_path / "watch.json")
    store = str(tmp_path / "store")
    main(["watch", "add", corpus, "--watchlist", wl])
    main(["daemon", "--once", "--watchlist", wl, "--store", store])
    capsys.readouterr()
    assert main(["digests", store]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["digests"][0]["responds_to"] == "vidA"


def test_cli_digests_on_empty_store_is_an_empty_list(tmp_path, capsys):
    from chorus.cli import main
    assert main(["digests", str(tmp_path / "empty-store")]) == 0
    assert json.loads(capsys.readouterr().out)["digests"] == []
