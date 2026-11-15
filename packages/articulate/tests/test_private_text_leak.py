"""The repository and the wheel carry no text from a private writing corpus.

The corpus is never in this repository. A maintainer who holds one points
ARTICULATE_LEAK_CORPUS at its folder and this test checks every 8-word shingle
of it against every tracked file and the built wheel. Without the variable the
corpus check skips; the scanner controls below always run, so a scanner that
stops matching fails here.

A shingle that already appears in the v0.7.0 release is Articulate's own text
quoted inside the corpus (a chat log that pastes a prompt, for example). Those
are counted apart and never fail the check. Messages carry counts only, never
matched text.
"""
import os
import pathlib
import re
import subprocess
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
N = 8
BASELINE_TAG = "v0.7.0"
_WORD = re.compile(r"[a-z0-9']+")


def shingles(text):
    w = _WORD.findall(text.lower())
    return {" ".join(w[i:i + N]) for i in range(len(w) - N + 1)}


def corpus_shingles(folder):
    out = set()
    for p in pathlib.Path(folder).rglob("*"):
        if p.is_file():
            out |= shingles(p.read_text(encoding="utf-8", errors="replace"))
    return out


def _git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


def tracked_texts():
    for name in _git("ls-files", "-z").decode("utf-8").split("\0"):
        path = ROOT / name
        if name and path.is_file():
            yield name, path.read_bytes().decode("utf-8", "replace")


def baseline_shingles(needles):
    found = set()
    for name in _git("ls-tree", "-r", "--name-only", BASELINE_TAG).decode("utf-8").splitlines():
        found |= shingles(_git("show", f"{BASELINE_TAG}:{name}").decode("utf-8", "replace")) & needles
    return found


def scan(texts, needles):
    hits = set()
    for _, text in texts:
        hits |= shingles(text) & needles
    return hits


def test_scanner_finds_a_planted_sentence(tmp_path):
    (tmp_path / "c.txt").write_text("the quiet harbor master counted eleven gulls before the tide "
                                    "turned at dawn", encoding="utf-8")
    needles = corpus_shingles(tmp_path)
    planted = [("x.md", "Notes. The quiet harbor master counted eleven gulls before the tide.")]
    assert scan(planted, needles)
    assert not scan([("y.md", "A different sentence about harbors and gulls entirely.")], needles)


def test_scanner_reads_zip_members(tmp_path):
    (tmp_path / "c.txt").write_text("one two three four five six seven eight nine", encoding="utf-8")
    z = tmp_path / "w.whl"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a/b.py", "# one two three four five six seven eight")
    with zipfile.ZipFile(z) as zf:
        members = [(n, zf.read(n).decode("utf-8", "replace")) for n in zf.namelist()]
    assert scan(members, corpus_shingles(tmp_path))


@pytest.mark.skipif(not os.environ.get("ARTICULATE_LEAK_CORPUS"),
                    reason="set ARTICULATE_LEAK_CORPUS to a private corpus folder to run")
def test_repo_and_wheel_hold_no_private_text(tmp_path):
    needles = corpus_shingles(os.environ["ARTICULATE_LEAK_CORPUS"])
    assert needles, "the corpus folder holds no text"
    texts = list(tracked_texts())
    builders = pytest.importorskip("hatchling.builders.wheel")
    wheel = next(iter(builders.WheelBuilder(str(ROOT)).build(directory=str(tmp_path),
                                                           versions=["standard"])))
    with zipfile.ZipFile(wheel) as zf:
        texts += [(n, zf.read(n).decode("utf-8", "replace")) for n in zf.namelist()]
    hits = scan(texts, needles)
    new = hits - baseline_shingles(hits)
    assert not new, f"{len(new)} shingles from the private corpus, absent from {BASELINE_TAG}"
