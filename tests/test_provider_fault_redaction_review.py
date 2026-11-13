"""False-success controls for durable provider fault records and bounded reads."""
import io
import json
import urllib.error

import pytest

from harness import model_faults, model_redaction
from harness.endpoints_http import _http
from harness.provider_fault_boundary import format_http_error

SECRET = "sk-proj-" + "synthetic" * 8


@pytest.mark.parametrize("body,headers", [
    ({"error": {"metadata": {SECRET: "detail"}}}, {}),
    ({"error": {"code": SECRET}}, {}),
    ({"StatusCode": 502, "Status": SECRET, "error": "upstream"}, {}),
    ({"error": "slow"}, {"retry-after": SECRET}),
])
def test_every_durable_fault_field_redacts_credentials(body, headers):
    record = model_faults.capture(status=401, dialect="openai", body=body,
                                  headers=headers)
    assert SECRET not in json.dumps(record)
    assert record["redacted"] is True
    assert "openai_project_key" in record["redacted_kinds"]


def test_key_truncation_collision_does_not_silently_overwrite_a_value():
    result = model_redaction.scrub_value({"a" * 30: "first", "a" * 31: "second"},
                                        limit=12)
    assert result["bounded"] is True
    assert all(len(key) <= 12 + len(model_redaction.TRUNCATED)
               for key in result["value"])
    assert "first" in result["value"].values()


class ReadProbe(io.BytesIO):
    def __init__(self, value):
        super().__init__(value)
        self.calls = []

    def read(self, *args):
        self.calls.append(args)
        return super().read(*args)


@pytest.mark.parametrize("route", ["formatter", "transport"])
def test_http_error_read_is_bounded_before_decode_and_scrubbing(route, monkeypatch):
    # A credential crosses the read boundary; omit a truncated body entirely.
    body = b"x" * (65536 - 10) + SECRET.encode() + b"x" * 100000
    stream = ReadProbe(body)
    error = urllib.error.HTTPError("https://provider.invalid", 502, "failed", {}, stream)
    if route == "formatter":
        result = format_http_error("codex", error)
        assert result.startswith("codex returned 502:")
    else:
        def fail(*args, **kwargs):
            raise error
        monkeypatch.setattr("urllib.request.urlopen", fail)
        status, result = _http("POST", "https://provider.invalid", {}, b"{}", 1)
        assert status == 502
    assert stream.calls == [(65537,)]
    assert stream.tell() == 65537
    assert "truncat" in str(result).lower()
    assert "sk-proj-" not in str(result)
