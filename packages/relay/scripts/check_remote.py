#!/usr/bin/env python3
"""check_remote.py — prove a relay remote MCP endpoint is publicly reachable and
connector-ready. Run it FROM MOBILE DATA (not home wifi) so it exercises the same
public path the Claude phone connector will:

    python scripts/check_remote.py https://relay.yourname.duckdns.org

It verifies the TLS handshake with a CA-valid cert, the OAuth protected-resource
metadata, and that /mcp answers (401 when unauthenticated is the healthy signal).
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request


def _request(url: str, method: str = "GET", data: bytes | None = None):
    req = urllib.request.Request(
        url, method=method, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def main(base: str) -> int:
    base = base.rstrip("/")
    if not base.startswith("https://"):
        print("FAIL: the URL must be https://")
        return 1
    ok = True

    try:
        status, body, _ = _request(base + "/.well-known/oauth-protected-resource")
        meta = json.loads(body)
        print(f"[ok] protected-resource metadata: HTTP {status}, resource={meta.get('resource')}")
        if meta.get("resource") != base + "/mcp":
            print(f"     note: RELAY_PUBLIC_URL should be {base!r} so resource == {base}/mcp")
    except ssl.SSLCertVerificationError as exc:
        print(f"[FAIL] TLS certificate is not publicly valid (self-signed?): {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - report any reachability failure
        print(f"[FAIL] metadata unreachable: {type(exc).__name__}: {exc}")
        ok = False

    try:
        status, _, headers = _request(base + "/mcp", method="POST", data=b"{}")
        auth = headers.get("WWW-Authenticate", "")
        print(f"[ok] /mcp reachable: HTTP {status} (401 is expected unauthenticated)"
              + (f", WWW-Authenticate present" if auth else ""))
    except ssl.SSLCertVerificationError as exc:
        print(f"[FAIL] TLS certificate is not publicly valid: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] /mcp unreachable: {type(exc).__name__}: {exc}")
        ok = False

    print("PASS — endpoint looks connector-ready" if ok
          else "FAIL — fix the above before adding the Claude connector")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/check_remote.py https://your-host")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
