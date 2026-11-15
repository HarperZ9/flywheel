import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest
from collections import Counter

from channel_router import (
    ChannelType,
    RouteDecision,
    ChannelRouter,
    ROUTE_TABLE,
)


def test_channel_type_enum_count():
    assert len(ChannelType) == 8


def test_route_table_covers_all_channels():
    for ch in ChannelType:
        assert ch in ROUTE_TABLE


def test_route_decision_fields():
    d = ROUTE_TABLE[ChannelType.STDIN]
    assert d.channel == ChannelType.STDIN
    assert d.tool == "safe_input"
    assert isinstance(d.cli_path, str)


def test_router_no_calibrate():
    router = ChannelRouter(no_calibrate=True)
    text, counts = router.calibrate_stdin("raw text here")
    assert text == "raw text here"
    assert counts == Counter()


def test_router_calibrate_stdout():
    router = ChannelRouter(no_calibrate=True)
    text, counts = router.calibrate_stdout("subprocess output")
    assert text == "subprocess output"


def test_router_route_file_read():
    router = ChannelRouter()
    decision = router.route_file("/some/path.py")
    assert decision.channel == ChannelType.FILE_R
    assert decision.tool == "safe_read"
    assert "/some/path.py" in decision.cli_path


def test_router_route_file_write():
    router = ChannelRouter()
    decision = router.route_file("/some/path.py", write=True)
    assert decision.channel == ChannelType.FILE_W
    assert decision.tool == "safe_write"


def test_router_route_url():
    router = ChannelRouter()
    decision = router.route_url("https://example.com/api")
    assert decision.channel == ChannelType.NETWORK
    assert decision.tool == "safe_fetch"
    assert "https://example.com/api" in decision.cli_path


def test_classify_input_url():
    assert ChannelRouter.classify_input("https://example.com") == ChannelType.NETWORK


def test_classify_input_file():
    assert ChannelRouter.classify_input("C:/dev/file.py") == ChannelType.FILE_R


def test_classify_input_stdin():
    assert ChannelRouter.classify_input("just some text") == ChannelType.STDIN
