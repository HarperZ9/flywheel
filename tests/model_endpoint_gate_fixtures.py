"""Profiles and a canned transport shared by the endpoint-gate test modules.

The gate's tests split into what the Ollama identity rules decide and what the
report says, and both halves build the same profile rows against the same fake
daemon. The shapes live here so the two modules cannot drift into describing
different daemons while claiming to test one gate.
"""
import hashlib
import json


def profile(backend="serve", model="14B"):
    selector = "qwen:14b"
    row = {
        "profile_id": f"{backend}-{model.lower()}", "model": model, "model_key": model.lower(),
        "model_ref": "serve:expected" if backend == "serve" else f"ollama:{selector}",
        "backend": backend, "provider_role": "flywheel", "endpoint_url": "http://127.0.0.1:8765",
    }
    if backend == "ollama":
        row["selectors"] = [selector]
        row["release_asset_sha256"] = "a" * 64
        row["expected_ollama_digest"] = "sha256:abc"
    return row


def write_profiles(tmp_path, rows):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"schema": "harness.model-endpoint-profiles/v1", "profiles": rows}), encoding="utf-8")
    return path


def transport(method, url, body, timeout):
    if url.endswith("/health"):
        return 200, {"ok": True, "model_ref": "serve:expected"}
    if url.endswith("/generate"):
        return 200, {"text": "active", "model_ref": "serve:expected", "seed": 0}
    if url.endswith("/api/tags"):
        return 200, {"models": [{"name": "qwen:14b", "digest": "sha256:abc"}]}
    if url.endswith("/api/chat"):
        return 200, {"message": {"content": "active"}, "model": "qwen:14b"}
    return 404, {}


def canonical_hash(row):
    encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
