"""Safetensors artifact IO for the optional encoder classifier."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.evidence_json import canonical_bytes, canonical_sha256, strict_load_json

from .classifier_encoder import EncoderClassifierError, EncoderClassifierModel, EncoderTrainingResult

ARTIFACT_SCHEMA = "flywheel.classifier-encoder-artifact/v1"
WEIGHTS = "model.safetensors"
MANIFEST = "manifest.json"
REPORT = "train_report.json"
ENCODER_CONFIG_DIR = "encoder_config"
TOKENIZER_DIR = "tokenizer"
MAX_MANIFEST_BYTES = 131_072
MAX_REPORT_BYTES = 1_000_000
MAX_RESOURCE_BYTES = 16_777_216
HEX = set("0123456789abcdef")
RESOURCE_FILES = {
    ENCODER_CONFIG_DIR: {"config.json"},
    TOKENIZER_DIR: {"tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
                    "vocab.txt", "merges.txt", "tokenizer.model", "added_tokens.json"},
}
MANIFEST_KEYS = {
    "schema", "artifact_identity", "weights_path", "weights_sha256",
    "training_report_path", "training_report_sha256", "source_model_ref",
    "bundled_resources", "families", "hidden_size", "max_length",
    "training_manifest_sha256", "provenance", "does_not_prove",
    "manifest_sha256",
}

@dataclass
class LoadedEncoderArtifact:
    model: Any
    tokenizer: Any
    report: dict
    manifest: dict


def _torch():
    try:
        import torch
    except ImportError as exc:
        raise EncoderClassifierError("torch is required for classifier encoder artifacts") from exc
    return torch


def _state_bytes(model: Any) -> bytes:
    from safetensors.torch import save

    tensors = {k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}
    return save(tensors)


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_bounded(path: Path, limit: int, label: str) -> bytes:
    try:
        with path.open("rb") as handle:
            raw = handle.read(limit + 1)
    except OSError as exc:
        raise EncoderClassifierError(f"invalid encoder artifact {label}") from exc
    if len(raw) > limit:
        raise EncoderClassifierError(f"encoder artifact {label} exceeds byte limit")
    return raw


def _hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and set(value) <= HEX


def _write(path: Path, value: dict) -> str:
    raw = canonical_bytes(value)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _copy_file(src: Path, dst: Path) -> str:
    raw = _read_bounded(src, MAX_RESOURCE_BYTES, "resource")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _bundle_resources(root: Path, pretrained_model_path: str | None) -> dict:
    resources = {ENCODER_CONFIG_DIR: {}, TOKENIZER_DIR: {}}
    if pretrained_model_path is None:
        return resources
    source = Path(pretrained_model_path)
    config = source / "config.json"
    if not config.is_file():
        raise EncoderClassifierError("pretrained encoder config missing")
    resources[ENCODER_CONFIG_DIR]["config.json"] = _copy_file(
        config, root / ENCODER_CONFIG_DIR / "config.json")
    for name in sorted(RESOURCE_FILES[TOKENIZER_DIR]):
        candidate = source / name
        if candidate.is_file():
            resources[TOKENIZER_DIR][name] = _copy_file(
                candidate, root / TOKENIZER_DIR / name)
    if not resources[TOKENIZER_DIR]:
        raise EncoderClassifierError("pretrained tokenizer bundle missing")
    return resources


def _manifest(result: EncoderTrainingResult, weights_sha: str,
              report_sha: str, source_ref: str | None, resources: dict) -> dict:
    body = {
        "schema": ARTIFACT_SCHEMA,
        "artifact_identity": result.report["artifact_identity"],
        "weights_path": WEIGHTS,
        "weights_sha256": weights_sha,
        "training_report_path": REPORT,
        "training_report_sha256": report_sha,
        "source_model_ref": source_ref,
        "bundled_resources": resources,
        "families": list(result.report["families"]),
        "hidden_size": int(result.model.hidden_size),
        "max_length": int(result.model.max_length),
        "training_manifest_sha256": result.report["training_manifest_sha256"],
        "provenance": {
            "format": "safetensors",
            "trust_remote_code": False,
            "local_files_only": True,
            "reference_compile": "not_used_transformers_5_12",
        },
        "does_not_prove": [
            "calibration, held-out workflow quality, authorization, or verifier acceptance",
        ],
    }
    return {**body, "manifest_sha256": canonical_sha256(body)}


def save_encoder_artifact(
    root: str | Path,
    result: EncoderTrainingResult,
    *,
    pretrained_model_path: str | None = None,
) -> dict:
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise EncoderClassifierError("encoder artifact requires a fresh directory")
    root.mkdir(parents=True, exist_ok=True)
    weights_path = root / WEIGHTS
    weights_raw = _state_bytes(result.model)
    weights_path.write_bytes(weights_raw)
    weights_sha = hashlib.sha256(weights_raw).hexdigest()
    if weights_sha != result.report.get("weights_sha256"):
        result.report = {**result.report, "weights_sha256": weights_sha,
                         "artifact_identity": f"classifier-encoder:{weights_sha[:16]}"}
    resources = _bundle_resources(root, pretrained_model_path)
    report_sha = _write(root / REPORT, result.report)
    manifest = _manifest(result, weights_sha, report_sha, pretrained_model_path, resources)
    _write(root / MANIFEST, manifest)
    return manifest


def _check_resource_manifest(resources: object) -> dict[str, dict[str, str]]:
    if type(resources) is not dict or set(resources) != set(RESOURCE_FILES):
        raise EncoderClassifierError("invalid encoder artifact manifest resources")
    checked: dict[str, dict[str, str]] = {}
    for section, allowed in RESOURCE_FILES.items():
        value = resources[section]
        if type(value) is not dict:
            raise EncoderClassifierError("invalid encoder artifact manifest resources")
        checked[section] = {}
        for name, digest in value.items():
            if type(name) is not str or name not in allowed or Path(name).name != name:
                raise EncoderClassifierError("invalid encoder artifact manifest resources")
            if not _hex64(digest):
                raise EncoderClassifierError("invalid encoder artifact manifest resources")
            checked[section][name] = digest
    return checked


def _check_manifest_shape(manifest: dict) -> dict:
    if type(manifest) is not dict or set(manifest) != MANIFEST_KEYS:
        raise EncoderClassifierError("invalid encoder artifact manifest")
    if manifest["schema"] != ARTIFACT_SCHEMA:
        raise EncoderClassifierError("invalid encoder artifact schema")
    if manifest["weights_path"] != WEIGHTS or manifest["training_report_path"] != REPORT:
        raise EncoderClassifierError("invalid encoder artifact manifest paths")
    for key in ("weights_sha256", "training_report_sha256", "training_manifest_sha256"):
        if not _hex64(manifest[key]):
            raise EncoderClassifierError("invalid encoder artifact manifest hashes")
    if type(manifest["artifact_identity"]) is not str or not manifest["artifact_identity"]:
        raise EncoderClassifierError("invalid encoder artifact manifest identity")
    if type(manifest["families"]) is not list or not manifest["families"]:
        raise EncoderClassifierError("invalid encoder artifact manifest families")
    if any(type(f) is not str or not f for f in manifest["families"]):
        raise EncoderClassifierError("invalid encoder artifact manifest families")
    if type(manifest["hidden_size"]) is not int or manifest["hidden_size"] <= 0:
        raise EncoderClassifierError("invalid encoder artifact manifest hidden size")
    if type(manifest["max_length"]) is not int or manifest["max_length"] <= 0:
        raise EncoderClassifierError("invalid encoder artifact manifest max length")
    if manifest["source_model_ref"] is not None and type(manifest["source_model_ref"]) is not str:
        raise EncoderClassifierError("invalid encoder artifact manifest source")
    _check_resource_manifest(manifest["bundled_resources"])
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    if manifest.get("manifest_sha256") != canonical_sha256(body):
        raise EncoderClassifierError("encoder artifact manifest checksum mismatch")
    return manifest


def _load_manifest(root: Path) -> dict:
    try:
        manifest = strict_load_json(
            _read_bounded(root / MANIFEST, MAX_MANIFEST_BYTES, "manifest"),
            max_bytes=MAX_MANIFEST_BYTES, max_depth=8)
    except (OSError, ValueError, RecursionError) as exc:
        raise EncoderClassifierError("invalid encoder artifact manifest") from exc
    return _check_manifest_shape(manifest)


def _validate_resources(root: Path, resources: dict) -> None:
    for section, files in _check_resource_manifest(resources).items():
        for name, digest in files.items():
            path = root / section / name
            raw = _read_bounded(path, MAX_RESOURCE_BYTES, "resource")
            if hashlib.sha256(raw).hexdigest() != digest:
                raise EncoderClassifierError("encoder artifact resource checksum mismatch")


def _validate_report(report: dict, manifest: dict) -> None:
    checks = {
        "artifact_identity": manifest["artifact_identity"],
        "weights_sha256": manifest["weights_sha256"],
        "training_manifest_sha256": manifest["training_manifest_sha256"],
        "families": manifest["families"],
        "max_length": manifest["max_length"],
    }
    for key, expected in checks.items():
        if report.get(key) != expected:
            raise EncoderClassifierError("encoder artifact report manifest mismatch")


def _load_bundled_backbone(root: Path, device: str):
    try:
        from transformers import AutoConfig, AutoModel, AutoTokenizer
    except ImportError as exc:
        raise EncoderClassifierError("transformers is required for bundled encoder loading") from exc
    config_dir, tokenizer_dir = root / ENCODER_CONFIG_DIR, root / TOKENIZER_DIR
    config = AutoConfig.from_pretrained(
        config_dir, local_files_only=True, trust_remote_code=False)
    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_dir, local_files_only=True, trust_remote_code=False)
    encoder = AutoModel.from_config(config, trust_remote_code=False).to(device)
    return tokenizer, encoder


def load_encoder_artifact(
    root: str | Path,
    *,
    tokenizer: Any | None = None,
    encoder: Any | None = None,
    device: str = "cpu",
) -> LoadedEncoderArtifact:
    torch = _torch()
    from safetensors.torch import load_file

    root = Path(root)
    manifest = _load_manifest(root)
    _validate_resources(root, manifest["bundled_resources"])
    weights_path = root / WEIGHTS
    report_path = root / REPORT
    if _sha_file(weights_path) != manifest["weights_sha256"]:
        raise EncoderClassifierError("encoder weights checksum mismatch")
    try:
        report = strict_load_json(
            _read_bounded(report_path, MAX_REPORT_BYTES, "report"),
            max_bytes=MAX_REPORT_BYTES, max_depth=12)
    except (OSError, ValueError, RecursionError) as exc:
        raise EncoderClassifierError("invalid encoder training report") from exc
    if hashlib.sha256(canonical_bytes(report)).hexdigest() != manifest["training_report_sha256"]:
        raise EncoderClassifierError("encoder report checksum mismatch")
    _validate_report(report, manifest)
    if tokenizer is None or encoder is None:
        if not manifest["bundled_resources"][ENCODER_CONFIG_DIR] or not manifest["bundled_resources"][TOKENIZER_DIR]:
            raise EncoderClassifierError("bundled encoder config and tokenizer required")
        tokenizer, encoder = _load_bundled_backbone(root, device)
    model = EncoderClassifierModel(
        encoder,
        list(manifest["families"]),
        max_length=int(manifest["max_length"]),
    ).to(device)
    state = load_file(str(weights_path), device=str(torch.device(device)))
    missing, unexpected = model.load_state_dict(state, strict=True)
    if missing or unexpected:
        raise EncoderClassifierError("encoder artifact state mismatch")
    return LoadedEncoderArtifact(model=model, tokenizer=tokenizer, report=report, manifest=manifest)
