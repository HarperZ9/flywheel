"""Known local model release and endpoint profile metadata."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


RELEASE_IDENTITY_PROVENANCE = Path(__file__).with_name("ollama-manifest-digest-provenance-v1.json")

_SHA256_DIGEST = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")


def ollama_reference(name: str) -> str:
    """Apply Ollama's own default-tag rule before two model names are compared.

    Ollama reads an untagged reference as `:latest` and always answers /api/tags
    with the qualified name, so comparing the two literally never matches and a
    pulled model reads as absent. The tag lives after the last slash, which keeps
    a registry host's port from being mistaken for one.
    """
    text = name.strip()
    if not text:
        return ""
    return text if ":" in text.rsplit("/", 1)[-1] else f"{text}:latest"


def ollama_digest_value(digest: object) -> str:
    """The digest's value, independent of how the daemon spelled it.

    Ollama has answered with both `sha256:<hex>` and a bare `<hex>` for the same
    manifest, so a profile recorded under one spelling fails against the other
    while naming identical bytes. Only that prefix is normalized: anything that
    is not a sha256 digest comes back unchanged and still fails the comparison.
    Callers read this out of untrusted JSON, so a value that is not a string is
    not a digest at all and is reported as absent rather than raising.
    """
    if not isinstance(digest, str):
        return ""
    match = _SHA256_DIGEST.match(digest.strip().lower())
    return match.group(1) if match else digest.strip()

MODEL_PROFILES = {
    "14b": {
        "model": "14B",
        "model_dir_name": "Qwen2.5-Coder-14B-Instruct",
        "model_ref": "Qwen2.5-Coder-14B-Instruct (base, nf4)",
        "serve_aliases": ["14b", "14b-base", "qwen2.5-coder-14b"],
        "ollama_selectors": ["qwen2.5-coder:14b", "qwen2.5-coder-14b", "14b"],
        "release": {
            "trained": True,
            "public_name": "Flywheel-Local-Coder-14B",
            "artifact_kind": "gguf-qlora-cpt-merge",
            "artifact_name": "telos-coder-14b-cpt2020-q4_k_m.gguf",
            "release_dir_name": "release/flywheel-local-coder-14b",
            "base_model": "Qwen2.5-Coder-14B-Instruct",
            "base_license": "Apache-2.0",
            "adapter": "checkpoint-2020 (QLoRA CPT, 2020 steps / 2 epochs; final logged loss 0.444, min 0.359)",
            "artifact_sha256": "613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be",
            "ollama_manifest_digest": "sha256:7ff88ed3fd95eac7e79cb38a0a5ee3db39b7103a09d5a51d75fcda908522f6d8",
            "ship_manifest": "tasks/research/gguf_ship_manifest_checkpoint2020.json",
            "ollama_model_name": "flywheel-local-coder-14b",
        },
    },
    "32b": {
        "model": "32B",
        "model_dir_name": "Qwen2.5-Coder-32B-Instruct",
        "model_ref": "Qwen2.5-Coder-32B-Instruct (base, nf4)",
        "serve_aliases": ["32b", "32b-base", "qwen2.5-coder-32b"],
        "ollama_selectors": ["qwen2.5-coder:32b", "qwen2.5-coder-32b", "32b"],
        "release": {
            "trained": True,
            "public_name": "Flywheel-Local-Coder-32B",
            "artifact_kind": "gguf-qlora-cpt-merge",
            "artifact_name": "telos-coder-32b-cpt2019-q4_k_m.gguf",
            "release_dir_name": "gguf-work-32b",
            "base_model": "Qwen2.5-Coder-32B-Instruct",
            "base_license": "Apache-2.0",
            "adapter": "checkpoint-2019 (QLoRA CPT, continued pretraining, 2019/2019 steps, completed 2026-07-12)",
            "artifact_sha256": "65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4",
            "ollama_manifest_digest": "sha256:35fa696e662eb83293491d4b87de1d1308254d82be7aa8244f4fa442bf0e09d9",
            "ship_manifest": "tasks/research/gguf_ship_manifest_checkpoint2019_32b.json",
            "ollama_model_name": "flywheel-local-coder-32b",
        },
    },
}


def model_key(model: str) -> str:
    return "".join(ch.lower() for ch in model if ch.isalnum())


def model_profile(model: str) -> dict:
    return dict(MODEL_PROFILES.get(model_key(model), {}))


def release_profile(model: str) -> dict:
    profile = MODEL_PROFILES.get(model_key(model), {})
    release = profile.get("release")
    return dict(release) if isinstance(release, dict) else {}


def validate_release_identity_provenance(path: Path = RELEASE_IDENTITY_PROVENANCE) -> dict:
    """Validate the durable digest receipt against release constants without probing Ollama."""
    try:
        receipt = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("release identity provenance unreadable") from exc
    if not isinstance(receipt, dict) or receipt.get("schema") != "harness.ollama-manifest-digest-provenance/v1":
        raise ValueError("release identity provenance schema mismatch")
    payload = {key: value for key, value in receipt.items() if key != "evidence_sha256"}
    evidence = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if receipt.get("evidence_sha256") != evidence:
        raise ValueError("release identity provenance evidence hash mismatch")
    derivation = receipt.get("derivation")
    expected_derivation = {"method": "sha256_exact_ollama_manifest_bytes", "source_kind": "Ollama manifest JSON bytes",
                           "tool": "python-stdlib-hashlib.sha256", "tool_version": "Python 3.12.10"}
    if derivation != expected_derivation:
        raise ValueError("release identity provenance derivation mismatch")
    expected = {profile["release"]["ollama_model_name"]: (profile["release"]["artifact_sha256"],
                profile["release"]["ollama_manifest_digest"]) for profile in MODEL_PROFILES.values()}
    rows = receipt.get("models") if isinstance(receipt.get("models"), list) else []
    observed = {row.get("native_model_name"): (row.get("release_asset_sha256"), row.get("ollama_manifest_digest"))
                for row in rows if isinstance(row, dict)}
    if len(observed) != len(rows) or observed != expected:
        raise ValueError("release identity provenance constants mismatch")
    return receipt


def release_root(model: str, base_root: Path) -> Path | None:
    release = release_profile(model)
    dir_name = str(release.get("release_dir_name", "")).strip()
    if not dir_name:
        return None
    return base_root / dir_name


def candidate_model_roots(model: str, base_root: Path) -> list[Path]:
    key = model_key(model)
    profile = model_profile(model)
    candidates = [
        base_root / model,
        base_root / model.lower(),
        base_root / key,
        base_root / f"model-{key}",
        base_root / f"local-{key}",
    ]
    if profile.get("model_dir_name"):
        candidates.extend([
            base_root / "models" / str(profile["model_dir_name"]),
            base_root / str(profile["model_dir_name"]),
        ])
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        text = str(path)
        if text not in seen:
            unique.append(path)
            seen.add(text)
    return unique
