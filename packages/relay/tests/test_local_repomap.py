"""Falsifiers for the repo map (the code-navigation context feature).

Load-bearing: (1) Python symbols (classes, functions, nested methods) are
extracted with line numbers; (2) noise dirs are ignored; (3) non-Python files are
listed, not parsed; (4) truncation past the file cap is reported, never silent;
(5) an unparseable file degrades to skipped, not a crash.
"""
from relay.local_repomap import build_repo_map


def test_extracts_python_symbols_with_lines(tmp_path):
    (tmp_path / "a.py").write_text(
        "class Foo:\n    def bar(self):\n        pass\n\ndef top():\n    return 1\n",
        encoding="utf-8")
    m = build_repo_map(str(tmp_path))
    assert "a.py" in m
    assert "class Foo (L1)" in m
    assert "def bar (L2)" in m
    assert "def top (L5)" in m


def test_ignores_noise_dirs(tmp_path):
    (tmp_path / "keep.py").write_text("def k():\n    pass\n", encoding="utf-8")
    noise = tmp_path / "__pycache__"
    noise.mkdir()
    (noise / "junk.py").write_text("def j():\n    pass\n", encoding="utf-8")
    m = build_repo_map(str(tmp_path))
    assert "keep.py" in m and "junk.py" not in m


def test_non_python_files_are_listed_not_parsed(tmp_path):
    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")
    m = build_repo_map(str(tmp_path))
    assert "other files:" in m and "README.md" in m


def test_truncation_is_reported(tmp_path):
    for i in range(6):
        (tmp_path / f"f{i}.py").write_text("def a():\n    pass\n", encoding="utf-8")
    m = build_repo_map(str(tmp_path), max_files=3)
    assert "truncated at 3 files" in m


def test_repo_map_has_hard_byte_bound_even_for_one_huge_identifier(tmp_path):
    huge_name = "f" + ("x" * 10000)
    (tmp_path / "huge.py").write_text(f"def {huge_name}():\n    pass\n", encoding="utf-8")

    m = build_repo_map(str(tmp_path), max_files=1, max_symbols=10, max_bytes=240)

    assert len(m.encode("utf-8")) <= 240
    assert "truncated at 240 bytes" in m


def test_scan_is_bounded_by_the_scan_cap(tmp_path, monkeypatch):
    # the walk stops at scan_cap (the huge-repo guard), not at the whole tree.
    def fake_walk(root):
        yield str(tmp_path), [], [f"f{i}.txt" for i in range(5)]
        raise AssertionError("walked past the scan cap")

    monkeypatch.setattr("relay.local_repomap.os.walk", fake_walk)

    m = build_repo_map(str(tmp_path), max_files=10, scan_cap=3)

    assert "f0.txt" in m and "f3.txt" not in m   # only the first 3 were scanned
    assert "scan bounded at 3 files" in m


def test_most_imported_file_ranks_in_even_when_named_last(tmp_path):
    # the old map kept the first files alphabetically, so a central file named 'zzz'
    # could be omitted under a tight cap. Ranking by import in-degree keeps it.
    (tmp_path / "zzz.py").write_text("def core():\n    return 1\n", encoding="utf-8")
    for i in range(5):
        (tmp_path / f"a{i}.py").write_text("import zzz\n", encoding="utf-8")
    m = build_repo_map(str(tmp_path), max_files=2)
    assert "zzz.py" in m and "def core (L1)" in m   # ranked in by in-degree, not name


def test_unparseable_file_is_skipped_not_fatal(tmp_path):
    (tmp_path / "bad.py").write_text("def (:\n", encoding="utf-8")   # syntax error
    (tmp_path / "good.py").write_text("def g():\n    pass\n", encoding="utf-8")
    m = build_repo_map(str(tmp_path))
    assert "good.py" in m and "def g" in m        # good file still mapped, no crash


def test_multi_language_symbols_via_regex(tmp_path):
    (tmp_path / "a.js").write_text("export function foo() {}\nclass Bar {}\n"
                                   "const add = (a, b) => a + b\n", encoding="utf-8")
    (tmp_path / "b.go").write_text("package m\nfunc (r *Repo) Save() {}\n"
                                   "func Baz() {}\ntype T struct {\n}\n", encoding="utf-8")
    (tmp_path / "c.rs").write_text("pub fn qux() {}\nstruct S {\n}\nimpl S {\n}\n", encoding="utf-8")
    (tmp_path / "d.ts").write_text("export interface Shape {}\nexport type Id = string\n"
                                   "enum Color {}\n", encoding="utf-8")
    (tmp_path / "e.cs").write_text("public class Widget {}\ninterface IThing {}\n", encoding="utf-8")
    m = build_repo_map(str(tmp_path))
    assert "fn foo (L1)" in m and "class Bar (L2)" in m and "fn add (L3)" in m   # js incl. arrow
    assert "fn Save (L2)" in m and "fn Baz (L3)" in m and "type T (L4)" in m     # go incl. method
    assert "fn qux (L1)" in m and "type S (L2)" in m and "impl S (L4)" in m      # rust incl. impl
    assert "iface Shape (L1)" in m and "type Id (L2)" in m and "enum Color (L3)" in m  # ts
    assert "type Widget (L1)" in m and "type IThing (L2)" in m                   # c#
    assert "other files:" not in m
