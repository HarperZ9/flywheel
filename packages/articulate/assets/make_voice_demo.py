"""Render docs/art/voice-intent-demo.gif from real command output.

    python assets/make_voice_demo.py

Runs `articulate voice check` on examples/voice-intent/flat.md and sharp.md in
process and draws each step as terminal frames. Needs Pillow, which is a
development tool here and never a package dependency.
"""
import contextlib
import io
import os
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from articulate import cli  # noqa: E402

W, H, PAD, LINE, ROWS, COLS = 1040, 600, 22, 21, 26, 112
GROUND, INK, DIM, DRIFT, PASS = "#111214", "#e6e4df", "#8b8a86", "#d9a54c", "#86b98f"
FONT = next((ImageFont.truetype(p, 15) for p in ("C:/Windows/Fonts/consola.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf") if Path(p).exists()), None)


def run(argv):
    buf, here = io.StringIO(), os.getcwd()
    os.chdir(ROOT)
    try:
        with contextlib.redirect_stdout(buf):
            cli.main(argv)
    finally:
        os.chdir(here)
    return wrap(buf.getvalue().splitlines())


def wrap(lines):
    out = []
    for line in lines:
        indent = " " * (len(line) - len(line.lstrip()) + (6 if line.lstrip().startswith("met") else 0))
        out += textwrap.wrap(line, COLS, subsequent_indent=indent) or [""]
    return out


def color(line):
    s = line.strip()
    if s.startswith("$"):
        return INK
    if "100/100" in s or s.startswith("met"):
        return PASS
    if s.startswith("miss") or "/100 against" in s:
        return DRIFT
    return INK if not s.startswith(("why:", "fix:", "line ", "Share of")) else DIM


def frame(lines):
    img = Image.new("RGB", (W, H), GROUND)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines[-ROWS:]):
        draw.text((PAD, PAD + i * LINE), line, fill=color(line), font=FONT)
    return img


def scene(shown, command, output):
    """Frames that type a command, then print its output a few lines at a time."""
    frames = []
    for n in range(0, len(command) + 1, 4):
        frames.append((frame(shown + ["$ " + command[:n]]), 40))
    shown = shown + ["$ " + command]
    for n in range(0, len(output), 3):
        frames.append((frame(shown + output[:n + 3]), 160))
    frames[-1] = (frames[-1][0], 3200)
    return frames, shown + output


def main():
    flat, sharp = "examples/voice-intent/flat.md", "examples/voice-intent/sharp.md"
    frames = []
    for path in (flat, sharp):
        body = wrap((ROOT / path).read_text(encoding="utf-8").splitlines())
        f1, shown = scene([], f"cat {path}", body)
        f2, _ = scene(shown + [""], f"articulate voice check {path} --intent zain",
                      run(["voice", "check", path, "--intent", "zain"]))
        frames += f1 + f2
    out = ROOT / "docs" / "art" / "voice-intent-demo.gif"
    frames[0][0].save(out, save_all=True, append_images=[f for f, _ in frames[1:]],
                      duration=[d for _, d in frames], loop=0, optimize=True)
    print(f"Wrote {out} ({len(frames)} frames, {sum(d for _, d in frames) / 1000:.0f} s)")


if __name__ == "__main__":
    main()
