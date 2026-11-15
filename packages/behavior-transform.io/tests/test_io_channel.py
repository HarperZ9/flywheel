import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import os
import re
import pytest
from unittest.mock import patch
from collections import Counter

from io_channel import _build_subs, _calibrate, _archive, main


def test_build_subs_empty():
    result = _build_subs({})
    assert result == []


def test_calibrate_no_subs():
    text, counter = _calibrate("hello world", [])
    assert text == "hello world"
    assert len(counter) == 0


def test_calibrate_with_subs():
    subs = [(re.compile(r"\bhello\b", re.IGNORECASE), "hi", "T1")]
    text, counter = _calibrate("hello world", subs)
    assert text == "hi world"
    assert counter["T1"] == 1


def test_calibrate_case_insensitive():
    subs = [(re.compile(r"\bHello\b", re.IGNORECASE), "hi", "T1")]
    text, counter = _calibrate("HELLO there", subs)
    assert text == "hi there"


def test_archive(tmp_path):
    os.chdir(tmp_path)
    _archive("test", "key", "content")
    cache = tmp_path / ".warden-safe-cache" / "io_channel" / "test"
    assert cache.exists()
    files = list(cache.iterdir())
    assert len(files) == 1
    assert files[0].read_text() == "content"


def test_main_dry_run(capsys):
    rc = main(["--dry-run", "--IO-off", "--", "echo", "hello"])
    assert rc == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["dry_run"] is True
    assert parsed["cmd"] == ["echo", "hello"]


def test_main_no_command():
    with pytest.raises(SystemExit):
        main(["--dry-run"])


def test_main_dry_run_no_calibrate(capsys):
    rc = main(["--dry-run", "--no-calibrate", "--", "echo", "test"])
    assert rc == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["calibrate"] is False


def test_main_dry_run_with_shell(capsys):
    rc = main(["--dry-run", "--shell", "--IO-off", "--", "echo", "test"])
    assert rc == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["shell"] is True


def test_build_subs_with_calibrations():
    class FakeCal:
        def __init__(self, orig, cal, sev):
            self.original = orig
            self.calibrated = cal
            self.severity = sev
    vm = {
        "CALIBRATIONS": [FakeCal("badword", "goodword", "tier1")],
        "KEEP_TERMS": [],
    }
    subs = _build_subs(vm)
    assert len(subs) == 1
    pat, dst, tier = subs[0]
    assert dst == "goodword"
    assert tier == "T1"


def test_build_subs_respects_keep_terms():
    class FakeCal:
        def __init__(self, orig, cal, sev):
            self.original = orig
            self.calibrated = cal
            self.severity = sev
    vm = {
        "CALIBRATIONS": [FakeCal("keep_me", "replaced", "tier1")],
        "KEEP_TERMS": ["keep_me"],
    }
    subs = _build_subs(vm)
    assert len(subs) == 0
