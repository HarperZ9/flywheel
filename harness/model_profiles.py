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
    },
    "32b": {
        "model": "32B",
        "model_dir_name": "Qwen2.5-Coder-32B-Instruct",
        "model_ref": "Qwen2.5-Coder-32B-Instruct (base, nf4)",
        "serve_aliases": ["32b", "32b-base", "qwen2.5-coder-32b"],
        "ollama_selectors": ["qwen2.5-coder:32b", "qwen2.5-coder-32b", "32b"],
    },
}


def model_key(model: str) -> str:
    return "".join(ch.lower() for ch in model if ch.isalnum())


def model_profile(model: str) -> dict:
    return dict(MODEL_PROFILES.get(model_key(model), {}))


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
