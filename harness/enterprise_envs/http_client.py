"""Small stdlib HTTP client used by enterprise environment E2E controls."""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request_json(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    raw_body: bytes | None = None,
    headers: dict[str, str] | None = None,
    expect_status: int,
) -> dict[str, Any]:
    if body is not None and raw_body is not None:
        raise ValueError("body_and_raw_body_conflict")
    data = raw_body
    if body is not None:
        data = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request = Request(url, data=data, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=10) as response:
            return {"status": response.status, "body": json.loads(response.read().decode("utf-8"))}
    except HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        if exc.code != expect_status:
            raise
        return {"status": exc.code, "body": payload}
