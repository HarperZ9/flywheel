"""The monotonic no-regression contract, tested without an LLM by injecting the
rewrite and judge functions. Uses a project-local temp dir (the pytest tmp_path
fixture's symlink management is denied on this Windows host)."""
import os
import shutil
import subprocess

import pytest

from articulate import editor

_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp")


@pytest.fixture()
def work():
    os.makedirs(_TMP, exist_ok=True)
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


def _scored(**kw):
    d = {"concreteness": 1, "commitment": 1, "economy": 1, "rhythm": 1,
         "restatable": 1, "worst": ["w"]}
    d.update(kw)
    return d


def _write(work, name, text):
    p = os.path.join(work, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def test_monotonic_accepts_improvement_then_rejects_regression(work):
    src = _write(work, "x.md", "draft text\n")
    out = os.path.join(work, "x.polished.md")
    scores = {
        "draft text": _scored(concreteness=2, commitment=2, economy=2, rhythm=2, restatable=2),
        "revised text": _scored(concreteness=4, commitment=4, economy=4, rhythm=4, restatable=4),
        "final text": _scored(concreteness=3, commitment=4, economy=4, rhythm=4, restatable=4),  # regresses
    }
    outputs = iter(["revised text", "final text"])
    editor.polish(src, out, passes=3, bar=5,
                  rewrite_fn=lambda t, mech, worst: next(outputs),
                  judge_fn=lambda t: scores.get(t.strip(), _scored()))
    # draft(2s) -> revised text(4s) accepted -> final text regresses concreteness (3<4) -> rejected, keep revised text
    assert _read(out).strip() == "revised text"


def test_bar_met_stops_early(work):
    src = _write(work, "y.md", "already good\n")
    out = os.path.join(work, "y.polished.md")

    def boom(*a):
        raise AssertionError("should not rewrite when the bar is already met")

    editor.polish(src, out, passes=3, bar=5, rewrite_fn=boom,
                  judge_fn=lambda t: _scored(concreteness=5, commitment=5, economy=5,
                                             rhythm=5, restatable=5))
    assert _read(out).strip() == "already good"


def test_injected_rewrite_is_still_guarded(work):
    src = _write(work, "numbers.md", "We shipped 14 items.\n")
    out = os.path.join(work, "numbers.polished.md")
    editor.polish(src, out, passes=1, bar=5,
                  rewrite_fn=lambda *a: "We shipped 15 items.",
                  judge_fn=lambda t: _scored())
    assert _read(out).strip() == "We shipped 14 items."


def test_narrative_mode_does_not_rewrite(work):
    src = _write(work, "n.md", "Some literary prose.\n")
    out = os.path.join(work, "n.polished.md")

    def boom(*a):
        raise AssertionError("narrative/narrate must not rewrite by default")

    editor.polish(src, out, passes=2, bar=5, mode="narrative/narrate",
                  rewrite_fn=boom, judge_fn=lambda t: _scored())
    assert _read(out) == "Some literary prose.\n"


@pytest.mark.parametrize("error", [editor.ClaudeUnavailable("claude CLI: rate limited"),
                                   subprocess.TimeoutExpired("claude", 600)])
def test_a_judge_failure_inside_the_loop_keeps_the_best_and_exits_cleanly(work, capsys, error):
    # The backend can drop halfway through the loop, for example on a rate
    # limit. That must end the loop with a message, not a traceback.
    src = _write(work, "z.md", "draft text\n")
    out = os.path.join(work, "z.polished.md")
    calls = []

    def judge(t):
        calls.append(t)
        if len(calls) > 1:
            raise error
        return _scored(concreteness=2, commitment=2, economy=2, rhythm=2, restatable=2)

    rc = editor.polish(src, out, passes=3, bar=5,
                       rewrite_fn=lambda t, mech, worst: "revised text", judge_fn=judge)
    assert rc == 0
    assert _read(out).strip() == "draft text"
    assert "judge failed" in capsys.readouterr().out
