"""Fakes shared by the claude_cli unit tests: a runner, a file table, a work folder."""
import os
import shutil

import pytest

_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_cli")
_SECRET = "value-that-must-not-leak-7f3a"
# Written out by hand so the test does not borrow the implementation's own set.
# tests/test_claude_cli_process.py checks both sets against cmd.exe itself.
_CMD_UNSAFE_EXPECTED = frozenset('"%^&|<>!\r\n')
_CMD_UNSAFE_UNQUOTED_EXPECTED = frozenset(")")
_LOCKDOWN_EXPECTED = ["--setting-sources", "user", "--strict-mcp-config", "--tools", ""]


class _Runner:
    def __init__(self, result=None, raises=None):
        self.calls, self.result, self.raises = [], result, raises
        self.prompt_file_text = self.cwd_listing = None

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        path = argv[argv.index("--append-system-prompt-file") + 1]
        with open(path, encoding="utf-8") as fh:
            self.prompt_file_text = fh.read()
        if kwargs.get("cwd") is not None:
            self.cwd_listing = os.listdir(kwargs["cwd"])
        if self.raises is not None:
            raise self.raises
        return self.result


class _Disk:
    """A fake file table that records every path the resolver probes."""

    def __init__(self, *paths):
        self.paths, self.probed = set(paths), []

    def __call__(self, path):
        self.probed.append(path)
        return path in self.paths


@pytest.fixture()
def work():
    os.makedirs(_TMP, exist_ok=True)
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)
