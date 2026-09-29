"""SP-15 for fold notes: a FoldIndex held in memory (a LocalAgent keeps one
for a whole session) re-reads the file under the custody lock before it adds
a span, so a note deleted meanwhile is not written back from the stale copy."""
from harness.fold_index import FoldIndex
from harness.trace_custody_lock import is_held


def _drop(path, span):
    other = FoldIndex(path)
    other.spans.pop(span)
    other._content.pop(span)
    for term in list(other.postings):
        other.postings[term].discard(span)
        if not other.postings[term]:
            del other.postings[term]
    other._save()


def test_a_stale_copy_does_not_write_a_deleted_span_back(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    (tmp_path / "home" / "state").mkdir(parents=True)
    path = tmp_path / "run" / "fold_index.json"
    held = FoldIndex(path)
    held.add("a" * 64, [{"role": "note", "content": "deleted fact"}])
    _drop(path, "a" * 64)
    held.add("b" * 64, [{"role": "note", "content": "new fact"}])
    on_disk = FoldIndex(path)
    assert set(on_disk.spans) == {"b" * 64}
    assert "deleted" not in path.read_text(encoding="utf-8")


def test_add_writes_under_the_custody_lock(tmp_path, monkeypatch):
    state = tmp_path / "home" / "state"
    state.mkdir(parents=True)
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    seen = []
    index = FoldIndex(tmp_path / "run" / "fold_index.json")
    real = index._save
    monkeypatch.setattr(index, "_save", lambda: seen.append(is_held(state)) or real())
    index.add("c" * 64, [{"role": "note", "content": "x"}])
    assert seen == [True]
