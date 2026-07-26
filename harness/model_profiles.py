"""Known local model release and endpoint profile metadata."""

from __future__ import annotations

from pathlib import Path


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
