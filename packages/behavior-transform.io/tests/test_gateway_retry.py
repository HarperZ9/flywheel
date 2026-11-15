import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from apparatus.gateway import ModelGateway


def _mock_send(responses: list[str]):
    """Mock urllib responses."""
    call_count = [0]

    def side_effect(req, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        body = json.dumps({
            "content": [{"type": "text", "text": responses[idx]}]
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    return side_effect


def test_chat_with_recovery_clean():
    gw = ModelGateway("anthropic")
    with patch("urllib.request.urlopen", side_effect=_mock_send(
        ["The answer is 42."]
    )):
        result = gw.chat_with_recovery(
            "test-model", [{"role": "user", "content": "question"}]
        )
    assert result.succeeded is True
    assert result.final_level == 0
    assert "42" in result.response


def test_chat_with_recovery_escalates():
    gw = ModelGateway("anthropic")
    with patch("urllib.request.urlopen", side_effect=_mock_send([
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
        "The answer is AES-256.",
    ])):
        result = gw.chat_with_recovery(
            "test-model", [{"role": "user", "content": "question"}]
        )
    assert result.succeeded is True
    assert result.final_level >= 1
    assert "AES-256" in result.response
