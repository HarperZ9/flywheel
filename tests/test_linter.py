"""The linter must find what is there and nothing that is not, and its
findings must re-check: a known-bad buffer yields the expected rules, a
clean file yields none, and the finding receipt is stable across runs."""

from harness import linter


def test_secret_and_danger_and_todo_are_found():
    text = (
        "api_key = 'ABCDEFGH123456789'\n"
        "eval(user_input)\n"
        "x = 1  # TODO: fix this\n"
    )
    fs = {f["rule"] for f in linter.lint_text("a.py", text)}
    assert "hardcoded-secret" in fs
    assert "dangerous-call" in fs
    assert "todo-marker" in fs


def test_swallowed_error_python():
    text = "try:\n    risky()\nexcept Exception:\n    pass\n"
    fs = {f["rule"] for f in linter.lint_text("a.py", text)}
    assert "swallowed-error" in fs


def test_function_too_long():
    body = "\n".join(f"    x{i} = {i}" for i in range(60))
    text = f"def big():\n{body}\n"
    fs = [f for f in linter.lint_text("a.py", text)
          if f["rule"] == "function-too-long"]
    assert len(fs) == 1
    assert "big" in fs[0]["message"]


def test_clean_file_has_no_findings():
    text = "def small(a, b):\n    return a + b\n"
    assert linter.lint_text("a.py", text) == []


def test_finding_receipt_is_stable():
    text = "eval(x)\n"
    a = linter.lint_text("a.py", text)[0]["receipt"]
    b = linter.lint_text("a.py", text)[0]["receipt"]
    assert a == b and len(a) == 16


def test_lint_project_root_hash_and_bad_root(tmp_path):
    (tmp_path / "bad.py").write_text("eval(x)\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("y = 1\n", encoding="utf-8")
    out = linter.lint_project(str(tmp_path))
    assert out["schema"] == "flywheel.lint/v1"
    assert out["n_findings"] >= 1
    assert out["by_severity"].get("high", 0) >= 1
    assert len(out["root_hash"]) == 64
    # Re-run: same content -> same root hash (re-checkable).
    again = linter.lint_project(str(tmp_path))
    assert again["root_hash"] == out["root_hash"]
    assert "error" in linter.lint_project(str(tmp_path / "nope"))
