"""Falsifiers for the docs site builder: complete, linked, escaped, current."""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from docsite_markdown import convert  # noqa: E402


def _builder():
    spec = importlib.util.spec_from_file_location("build_docs_site",
                                                  ROOT / "scripts" / "build_docs_site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.timeout(240)
def test_the_site_builds_with_every_command_and_no_broken_link(tmp_path):
    b = _builder()
    problems = b.build(tmp_path)
    assert problems == []
    pages = {p.name for p in tmp_path.glob("*.html")}
    assert pages == {page for *_x, page in b.PAGES}
    commands = (tmp_path / "commands.html").read_text(encoding="utf-8")
    for name in b.command_names():
        assert f'id="flywheel-{name}"' in commands, name
    footer = re.search(r"Flywheel ([0-9.]+)\. Built", commands).group(1)
    assert footer == b.version()


def test_markdown_escapes_html_and_rewrites_site_links():
    out, heads = convert("# Title <x>\n\nSee [code](docs/CODE-SESSION.md#undo) and "
                         "<script>alert(1)</script> `a<b`.\n\n| a | b |\n|---|---|\n| 1 | 2 |",
                         link_map={"docs/CODE-SESSION.md": "code.html"})
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert 'href="code.html#undo"' in out and "<code>a&lt;b</code>" in out
    assert "<table>" in out and heads[0][0] == 1


def test_unknown_md_links_point_at_the_repository():
    out, _ = convert("[x](LICENSE)", link_map={})
    assert 'href="https://github.com/HarperZ9/flywheel/blob/main/LICENSE"' in out


def test_relative_links_resolve_from_the_source_folder():
    out, _ = convert("[l](../LICENSE)", link_map={}, here="docs/LICENSING.md")
    assert "blob/main/LICENSE" in out and ".." not in out
