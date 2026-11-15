from __future__ import annotations

from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .models import GuardedFetchResult
from .receipts import GuardrailReceipt
from .redaction import GuardrailPolicy


def fetch_guarded(
    url: str,
    *,
    timeout: float = 10,
    max_bytes: int = 1_000_000,
    policy: GuardrailPolicy | None = None,
) -> GuardedFetchResult:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http and https URLs are allowed")
    request = Request(url, headers={"User-Agent": "secret-redact-io/0.1"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError(f"response exceeded max_bytes={max_bytes}")
        status = int(response.status)
        content_type = response.headers.get("Content-Type", "")
    text = raw.decode("utf-8", errors="replace")
    redacted = (policy or GuardrailPolicy.default()).redact_text(text)
    receipt = GuardrailReceipt.create(
        operation="fetch",
        target=f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
        raw_bytes=raw,
        redacted_text=redacted.text,
        redactions=redacted.counts,
        metadata={"content_type": content_type, "status_code": status},
    )
    return GuardedFetchResult(text=redacted.text, status_code=status, receipt=receipt)
