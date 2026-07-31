"""The LSP bridge must speak real framing and fail honestly: a scripted
server answers definition and hover through the full stack, a dead command
is a named error, and a bad method never reaches the wire."""

import sys
from pathlib import Path

from harness.lsp_bridge import lsp_query

FAKE = [sys.executable, str(Path(__file__).parent / "fake_lsp_server.py")]


def test_definition_roundtrip_through_real_framing(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    out = lsp_query(FAKE, str(tmp_path), str(f), "x = 1\n", "python",
                    "definition", 0, 0)
    assert out.get("error") is None, out
    loc = out["result"][0]
    assert loc["range"]["start"]["line"] == 2
    assert loc["uri"].endswith("a.py")


def test_hover_roundtrip(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    out = lsp_query(FAKE, str(tmp_path), str(f), "x = 1\n", "python",
                    "hover", 0, 0)
    assert out["result"]["contents"]["value"] == "fake hover"


def test_dead_command_is_a_named_error(tmp_path):
    out = lsp_query(["definitely-not-a-language-server-xyz"], str(tmp_path),
                    str(tmp_path / "a.py"), "", "python", "definition", 0, 0)
    assert "error" in out


def test_bad_method_and_bad_root_are_refused(tmp_path):
    out = lsp_query(FAKE, str(tmp_path), str(tmp_path / "a.py"), "", "python",
                    "rename", 0, 0)
    assert "error" in out
    out = lsp_query(FAKE, str(tmp_path / "nope"), "a.py", "", "python",
                    "definition", 0, 0)
    assert "error" in out


def test_the_bridge_cache_is_closed_at_exit():
    """The cache is keyed by (command, root) and outlives any single call, which
    is what makes a second query fast. Nothing ended those processes, so every
    distinct key leaked a language server for the life of the interpreter: a test
    session left them running after it exited. close_all is registered at exit,
    and it must actually reap what the cache holds."""
    import atexit
    from harness import lsp_bridge

    b = lsp_bridge.get_bridge(FAKE, str(Path(__file__).parent))
    assert b.alive()
    assert lsp_bridge._BRIDGES, "the bridge was not cached"

    closed = lsp_bridge.close_all()
    assert closed >= 1
    assert lsp_bridge._BRIDGES == {}, "the cache still holds a dead bridge"
    b._proc.wait(timeout=10)
    assert not b.alive(), "the server survived close_all"

    # Idempotent: a second call has nothing to do and must not raise.
    assert lsp_bridge.close_all() == 0


# NOT TESTED HERE, deliberately, and worth saying why rather than leaving a
# confident-looking gap. An earlier version of this file asserted that a child
# process exiting leaves no language server behind. It passed with the atexit
# registration REMOVED, so it was proving nothing: a server whose client dies
# loses its stdin and exits on EOF by itself. The exit path was never the leak.
#
# The leak that is real is accumulation DURING a long life. The cache is keyed by
# (command, root) and never evicted, so a gateway or editor session that opens
# bridges across many roots holds every one of them open for as long as it runs.
# close_all() is what a long-lived caller now has to reap them, and the test above
# covers exactly that. The atexit hook is belt and braces for shutdown, and it is
# not load-bearing enough to justify a test that would need a deliberately
# EOF-ignoring fake server to mean anything.
