"""The academy's pedagogy engine: turn a lesson into a runnable manim scene.

The generator is deterministic and its output must be valid, runnable Python; a
lesson with no steps still writes its title; a bad scene name is sanitized to a
real identifier; and rendering fails honestly when manimgl is absent.
"""

from harness.manim_lesson import lesson_to_manim, render_lesson


def test_generated_scene_compiles_and_carries_the_lesson():
    lesson = {
        "title": "Euler's Identity",
        "scene_name": "EulerIdentity",
        "steps": [
            {"tex": r"e^{i\pi} + 1 = 0", "caption": "the most beautiful equation"},
            {"tex": r"e^{i\theta} = \cos\theta + i\sin\theta", "caption": "Euler's formula"},
        ],
    }
    import json
    src = lesson_to_manim(lesson)
    compile(src, "<generated>", "exec")               # must be runnable Python
    assert "class EulerIdentity(Scene)" in src
    assert "def construct(self)" in src
    # the LaTeX is embedded as a safe literal that evaluates back to the exact tex
    assert json.dumps(r"e^{i\pi} + 1 = 0") in src
    assert "the most beautiful equation" in src


def test_a_titleless_or_stepless_lesson_still_generates_a_valid_scene():
    src = lesson_to_manim({"title": "Empty", "scene_name": "Empty", "steps": []})
    compile(src, "<generated>", "exec")
    assert "class Empty(Scene)" in src


def test_a_bad_scene_name_is_sanitized_to_an_identifier():
    src = lesson_to_manim({"title": "T", "scene_name": "3 bad-name!", "steps": []})
    # the class name must be a valid identifier, never the raw string
    import re
    m = re.search(r"class (\w+)\(Scene\)", src)
    assert m and m.group(1).isidentifier()


def test_quotes_and_backslashes_in_content_do_not_break_the_source():
    src = lesson_to_manim({"title": 'a "quoted" title', "scene_name": "S",
                           "steps": [{"tex": r"\frac{a}{b}", "caption": 'he said "hi"'}]})
    compile(src, "<generated>", "exec")


def test_render_is_a_named_null_when_manimgl_is_absent(tmp_path):
    # a runner that reports manimgl missing (mirrors a real absent-tool path)
    out = render_lesson("from manimlib import *\n", "S", str(tmp_path),
                        runner=lambda cmd: (127, "", "manimgl: not found"))
    assert "error" in out


def test_render_returns_the_output_on_success(tmp_path):
    out = render_lesson("from manimlib import *\n", "S", str(tmp_path),
                        runner=lambda cmd: (0, "written to S.mp4", ""))
    assert out.get("error") is None
    assert out["scene"] == "S"
