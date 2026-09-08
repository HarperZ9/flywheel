"""Check the actual frozen gateway before packaging it into an installer.

Uses an isolated profile, local bearer and synthetic invalid identity. It never
creates/registers an identity or contacts model providers. This checks the
onedir payload, not installer behavior, clean-OS compatibility or Relay runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

SYNTHETIC_KEY = "SYNTHETIC_INVALID_FROZEN_GATEWAY_SMOKE_NOT_A_KEY"
NATIVE_ROUTES = {
    "/api/bulletin-identity": "get",
    "/api/bulletin-identity/create": "post",
    "/api/bulletin-identity/register": "post",
}


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def validate_documents(identity, spec, card, llms, *, expected_version: str):
    """Reject success-shaped replies that lack the shipped capability."""
    require(isinstance(identity, dict), "IDENTITY_SHAPE")
    require(set(identity) <= {
        "schema", "credential_name", "source", "keychain_available",
        "signing_available", "create_available", "register_available",
        "unavailable_reason",
    }, "IDENTITY_UNEXPECTED_FIELD")
    require(identity.get("schema") == "flywheel.bulletin-identity-status/v1",
            "IDENTITY_SCHEMA")
    require(identity.get("source") == "env", "IDENTITY_SOURCE")
    require(identity.get("signing_available") is True, "SIGNING_UNAVAILABLE")
    require(identity.get("create_available") is False
            and identity.get("register_available") is False
            and identity.get("unavailable_reason") == "ENV_CREDENTIAL_PRESENT",
            "ENV_IDENTITY_NOT_PROTECTED")
    require(spec.get("openapi") == "3.1.0", "OPENAPI_SHAPE")
    require(spec.get("info", {}).get("version") == expected_version,
            "OPENAPI_VERSION")
    paths = spec.get("paths", {})
    require(isinstance(paths, dict) and bool(paths), "EMPTY_OPENAPI")
    for path, method in NATIVE_ROUTES.items():
        require(method in paths.get(path, {}), "NATIVE_ROUTE_MISSING")
        require(paths[path][method].get("security") == [{"bearerAuth": []}],
                "NATIVE_ROUTE_CUSTODY")
        require(path in llms, "LLMS_NATIVE_ROUTE_MISSING")
    require(card.get("schema") == "flywheel.discovery/v1", "CARD_SCHEMA")
    require(card.get("version") == expected_version, "CARD_VERSION")
    require(card.get("routes") == len(paths), "CARD_ROUTE_COUNT")
    require(card.get("discovery") == {
        "openapi": "/openapi.json", "llms_txt": "/llms.txt",
    }, "CARD_LINKS")
    require(expected_version in llms and len(llms.strip()) > 40, "LLMS_VERSION")


def _environment(home: Path) -> dict[str, str]:
    retained = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE"}
    env = {k: v for k, v in os.environ.items() if k.upper() in retained}
    env.update({"FLYWHEEL_HOME": str(home), "USERPROFILE": str(home),
                "HOME": str(home), "TMP": str(home), "TEMP": str(home),
                "APPDATA": str(home), "LOCALAPPDATA": str(home),
                "BULLETIN_AGENT_JWK": SYNTHETIC_KEY,
                "PATH": str(Path(os.environ.get("SystemRoot", "/")) / "System32")})
    return env


def _request(base: str, path: str, token: str | None):
    headers = {"Authorization": "Bearer " + token} if token else {}
    # Never use ambient proxies for this exclusively loopback probe.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(base + path, headers=headers)
    try:
        response = opener.open(request, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read(2_000_001)
        require(len(raw) <= 2_000_000, "OVERSIZED_RESPONSE")
        body = raw.decode("utf-8")
        require(SYNTHETIC_KEY not in body and (not token or token not in body),
                "CREDENTIAL_ECHO")
        return response.code, body


def check(executable: Path, expected_version: str, receipt: dict) -> None:
    require(executable.is_file(), "EXECUTABLE_MISSING")
    receipt["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    # TemporaryDirectory owns only its newly allocated child; no supplied path
    # is recursively removed. The owned process is terminal before cleanup.
    with tempfile.TemporaryDirectory(prefix="flywheel-frozen-smoke-") as directory:
        home = Path(directory).resolve()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = _environment(home)
        process = subprocess.Popen([
            str(executable), "--host", "127.0.0.1", "--port", str(port),
            "--root", str(home), "--run-root", str(home / "runs"),
            "--serve-url", "http://127.0.0.1:1", "--ollama-url", "http://127.0.0.1:1",
        ], cwd=home, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 30
            token_path = home / "gateway.token"
            while time.monotonic() < deadline:
                require(process.poll() is None, "GATEWAY_EXITED")
                if token_path.is_file():
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=.2):
                            break
                    except OSError:
                        pass
                time.sleep(.1)
            else:
                raise RuntimeError("STARTUP_TIMEOUT")
            token = token_path.read_text(encoding="utf-8").strip()
            require(len(token) >= 32, "LOCAL_TOKEN_INVALID")
            base = f"http://127.0.0.1:{port}"
            status, body = _request(base, "/api/bulletin-identity", None)
            require(token not in body, "CREDENTIAL_ECHO")
            require(status == 401 and json.loads(body).get("error", {}).get("code")
                    == "AUTH_REQUIRED", "PRIVATE_AUTH_NOT_ENFORCED")
            receipt["unauthenticated_identity_status"] = status
            docs = []
            for path in ("/api/bulletin-identity", "/openapi.json",
                         "/.well-known/flywheel.json", "/llms.txt"):
                status, body = _request(base, path, token)
                receipt.setdefault("authenticated_statuses", {})[path] = status
                require(status == 200, "HTTP_FAILURE:" + path)
                docs.append(body if path == "/llms.txt" else json.loads(body))
            validate_documents(*docs, expected_version=expected_version)
            receipt.update(signing_imports_available=True, identity_source="env",
                           version=docs[2]["version"], routes=docs[2]["routes"],
                           native_routes=list(NATIVE_ROUTES), credential_echo=False)
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            receipt["owned_process_terminal"] = process.poll() is not None
    receipt["isolated_runtime_removed"] = not home.exists()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = {"schema": "flywheel.frozen-gateway-smoke/v1", "verdict": "HOLD",
               "expected_version": args.expected_version,
               "does_not_prove": ["installer integration", "clean OS compatibility",
                                  "native identity registration", "Relay execution"]}
    try:
        check(args.executable.resolve(), args.expected_version, receipt)
        receipt["verdict"] = "PASS"
    except Exception as exc:
        # Our fixed failure codes are safe; arbitrary OS/server messages are not.
        receipt["failure"] = str(exc) if type(exc) is RuntimeError else type(exc).__name__
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))
    return 0 if receipt["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
