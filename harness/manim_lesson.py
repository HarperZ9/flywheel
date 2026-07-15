"""manim_lesson.py -- the academy's pedagogy engine: a lesson -> a runnable manim scene.

A lesson is a title plus an ordered list of steps (a LaTeX line, optionally a caption).
``lesson_to_manim`` generates a deterministic, runnable manimgl ``Scene`` that writes the
title, then reveals each step's equation in order beneath its caption. It generates the
CODE and hands it back: the human reads and runs it, the process revealed rather than a
video produced behind a curtain (learning woven into the work). ``render_lesson`` drives
manimgl when it is installed and reports an honest null when it is not -- nothing is
faked, and a missing tool is named, never a silent success.

This ties manim (3Blue1Brown's programmatic math-animation engine) into the learn lane:
the flagship turns an equation-bearing lesson into an animation a learner can run and edit.
Zero-dep generation (stdlib only); manimgl is needed only to RENDER.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

_TIMEOUT = 300


def _identifier(name: str, *, fallback: str = "LessonScene") -> str:
    """A valid Python class identifier from arbitrary text: keep word chars, drop the
    rest, ensure it does not start with a digit, fall back if nothing usable remains."""
    cleaned = re.sub(r"\W", "", (name or "").replace(" ", ""))
    if not cleaned or cleaned[0].isdigit():
        cleaned = fallback + cleaned
    return cleaned if cleaned.isidentifier() else fallback


def _lit(value: str) -> str:
    """A safe Python string literal for arbitrary content (quotes, backslashes, TeX)."""
    return json.dumps(str(value), ensure_ascii=False)


def lesson_to_manim(lesson: dict) -> str:
    """Generate a runnable manimgl Scene source for a lesson. Deterministic."""
    title = str(lesson.get("title", ""))
    scene = _identifier(str(lesson.get("scene_name", "") or title))
    steps = lesson.get("steps") if isinstance(lesson.get("steps"), list) else []

    lines = [
        "from manimlib import *",
        "",
        "",
        f"class {scene}(Scene):",
        "    def construct(self):",
        f"        title = Text({_lit(title)})",
        "        self.play(Write(title))",
        "        self.wait()",
        "        self.play(title.animate.to_edge(UP))",
    ]
    prev = "title"
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        tex = str(step.get("tex", ""))
        caption = str(step.get("caption", ""))
        eq, cap = f"eq{i}", f"cap{i}"
        lines += [
            f"        {eq} = Tex({_lit(tex)})",
            f"        self.play(FadeIn({eq}, shift=DOWN))",
        ]
        if caption:
            lines += [
                f"        {cap} = Text({_lit(caption)}).scale(0.6).next_to({eq}, DOWN)",
                f"        self.play(FadeIn({cap}))",
            ]
        lines += ["        self.wait()"]
        if prev not in ("title",):
            lines.insert(len(lines), f"        self.play(FadeOut({prev}))")
        prev = eq
    lines += ["        self.wait(2)", ""]
    return "\n".join(lines)


def scene_name(lesson: dict) -> str:
    """The class name a lesson's generated scene will carry (a valid identifier)."""
    return _identifier(str(lesson.get("scene_name", "") or lesson.get("title", "")))


def manimgl_available() -> bool:
    return _manimgl_argv() is not None


def _manimgl_argv() -> "list | None":
    exe = shutil.which("manimgl")
    return [exe] if exe else None


def render_lesson(scene_src: str, scene: str, out_dir: str, *, runner=None) -> dict:
    """Render a generated scene with manimgl (write mode). Returns the scene name and
    the output tail, or a named error when manimgl is absent or the render fails."""
    scene = _identifier(scene)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{scene}.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(scene_src)
    argv = _manimgl_argv()
    if runner is None and argv is None:
        return {"error": "manimgl is not installed; pip install manimgl (needs FFmpeg + LaTeX)"}
    cmd = (argv or ["manimgl"]) + [path, scene, "-w"]
    try:
        if runner is not None:
            rc, out, err = runner(cmd)
        else:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT, cwd=out_dir)
            rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return {"error": f"manimgl render timed out after {_TIMEOUT}s"}
    except (OSError, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"}
    if rc != 0:
        return {"error": f"manimgl render failed (rc {rc}): {(err or out or '').strip()[-300:]}"}
    return {"scene": scene, "source": path, "output": (out or "").strip()[-300:]}
