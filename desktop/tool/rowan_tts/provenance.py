from __future__ import annotations

import ctypes
import hashlib
import json
import math
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any

DEFAULT_MODEL_REPO = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
DEFAULT_MODEL_REVISION = "5ecdb67327fd37bb2e042aab12ff7391903235d3"
DEFAULT_BASE_MODEL_REPO = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
DEFAULT_BASE_MODEL_REVISION = "fd4b254389122332181a7c3db7f27e918eec64e3"
DEFAULT_PROFILE = "rowan-draft-adjustable-20260915"
DEFAULT_VOICE_PROMPT = (
    "Original adult Australian male voice with a strong natural Australian "
    "English accent. Warm grounded baritone, clear relaxed consonants, broad "
    "Australian vowels, friendly expressive rhythm, and an approachable "
    "conversational pace. Avoid parody, forced slang, catchphrases, celebrity "
    "likeness, named-person imitation, or commercial-voice imitation."
)
DEFAULT_GENERATION: dict[str, Any] = {
    "do_sample": True,
    "top_k": 50,
    "top_p": 0.92,
    "temperature": 0.86,
    "repetition_penalty": 1.05,
    "subtalker_dosample": True,
    "subtalker_top_k": 50,
    "subtalker_top_p": 0.92,
    "subtalker_temperature": 0.86,
    "max_new_tokens": 4096,
}
FORBIDDEN_SOURCE_TOKENS = ("cartesia", "heath", "steve", "irwin")
EXPECTED_MODEL_CONFIG = {
    "model_type": "qwen3_tts",
    "tokenizer_type": "qwen3_tts_tokenizer_12hz",
    "tts_model_size": "1b7",
    "tts_model_type": "voice_design",
}
REQUIRED_MODEL_FILES = (
    "README.md",
    "config.json",
    "generation_config.json",
    "model.safetensors",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "speech_tokenizer/config.json",
    "speech_tokenizer/configuration.json",
    "speech_tokenizer/model.safetensors",
    "speech_tokenizer/preprocessor_config.json",
)
GENERATION_LIMITS: dict[str, tuple[str, float, float]] = {
    "top_k": ("int", 1, 200),
    "top_p": ("float", 0.05, 1.0),
    "temperature": ("float", 0.05, 2.0),
    "repetition_penalty": ("float", 0.8, 2.0),
    "subtalker_top_k": ("int", 1, 200),
    "subtalker_top_p": ("float", 0.05, 1.0),
    "subtalker_temperature": ("float", 0.05, 2.0),
    "max_new_tokens": ("int", 1, 8192),
}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def reject_source_tokens(field: str, value: str) -> None:
    lower = value.lower()
    for token in FORBIDDEN_SOURCE_TOKENS:
        if token in lower:
            raise ValueError(f"{field} contains disallowed source token")


def sanitize_generation(value: Any) -> dict[str, Any]:
    if value is None:
        return dict(DEFAULT_GENERATION)
    if not isinstance(value, dict):
        raise ValueError("generation must be an object")
    out = dict(DEFAULT_GENERATION)
    for key, item in value.items():
        if key not in DEFAULT_GENERATION:
            raise ValueError(f"unsupported generation key: {key}")
        if isinstance(DEFAULT_GENERATION[key], bool):
            if not isinstance(item, bool):
                raise ValueError(f"{key} must be bool")
        else:
            _validate_numeric_generation(key, item)
        out[key] = item
    return out


def _validate_numeric_generation(key: str, item: Any) -> None:
    kind, low, high = GENERATION_LIMITS[key]
    if kind == "int":
        if type(item) is not int:
            raise ValueError(f"{key} must be an integer")
    elif type(item) not in {int, float}:
        raise ValueError(f"{key} must be numeric")
    value = float(item)
    if not math.isfinite(value):
        raise ValueError(f"{key} must be finite")
    if value < low or value > high:
        raise ValueError(f"{key} must be between {low:g} and {high:g}")


def verify_model_dir_identity(
    model_dir: Path,
    expected_revision: str,
    *,
    repo_id: str = DEFAULT_MODEL_REPO,
    tts_model_type: str = "voice_design",
) -> dict[str, Any]:
    missing = [name for name in REQUIRED_MODEL_FILES if not (model_dir / name).exists()]
    if missing:
        raise RuntimeError(f"model_dir missing required files: {missing}")
    config_path = model_dir / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    expected_config = dict(EXPECTED_MODEL_CONFIG)
    expected_config["tts_model_type"] = tts_model_type
    mismatches = {
        key: {"expected": expected, "actual": config.get(key)}
        for key, expected in expected_config.items()
        if config.get(key) != expected
    }
    if mismatches:
        raise RuntimeError(f"model_dir config mismatch: {mismatches}")
    readme = (model_dir / "README.md").read_text(encoding="utf-8", errors="replace")
    if "license: apache-2.0" not in readme.lower():
        raise RuntimeError("model_dir README does not record apache-2.0 license")
    metadata_root = model_dir / ".cache" / "huggingface" / "download"
    metadata = {}
    for file_name in REQUIRED_MODEL_FILES:
        meta_path = metadata_root / f"{file_name}.metadata"
        if not meta_path.exists():
            raise RuntimeError(f"model_dir missing metadata: {meta_path}")
        revision = meta_path.read_text(encoding="utf-8").splitlines()[0].strip()
        metadata[file_name] = revision
    bad = {
        name: revision
        for name, revision in metadata.items()
        if revision != expected_revision
    }
    if bad:
        raise RuntimeError(f"model_dir metadata revision mismatch: {bad}")
    return {
        "repo_id": repo_id,
        "revision": expected_revision,
        "model_dir": str(model_dir),
        "config": {key: config.get(key) for key in expected_config},
        "required_files": {
            name: {"bytes": (model_dir / name).stat().st_size}
            for name in REQUIRED_MODEL_FILES
        },
        "metadata_files_checked": len(metadata),
        "license": "apache-2.0",
    }


def ram_snapshot() -> dict[str, Any]:
    if sys.platform != "win32":
        return {"available": False, "reason": "not_windows"}

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(MemoryStatusEx)
    ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    if not ok:
        return {"available": False, "reason": "GlobalMemoryStatusEx_failed"}
    gb = 1024 ** 3
    return {
        "available": True,
        "total_gb": round(status.ullTotalPhys / gb, 3),
        "available_gb": round(status.ullAvailPhys / gb, 3),
        "percent": int(status.dwMemoryLoad),
    }


def gpu_snapshot() -> dict[str, Any]:
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,memory.free,"
        "utilization.gpu,temperature.gpu,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, check=True, text=True, timeout=5
        )
        parts = [part.strip() for part in proc.stdout.splitlines()[0].split(",")]
        return {
            "available": True,
            "name": parts[0],
            "memory_total_mib": int(parts[1]),
            "memory_used_mib": int(parts[2]),
            "memory_free_mib": int(parts[3]),
            "utilization_gpu_percent": int(parts[4]),
            "temperature_c": int(parts[5]),
            "driver_version": parts[6],
        }
    except Exception as exc:
        return {"available": False, "error": repr(exc)}


def wav_info(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        frame_rate = wav.getframerate()
        frames = wav.getnframes()
        data = wav.readframes(frames)
    rms = _pcm_rms(data, sample_width)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "sample_rate": frame_rate,
        "wave_header": {
            "channels": channels,
            "sample_width_bytes": sample_width,
            "frame_rate": frame_rate,
            "frames": frames,
            "duration_s": frames / frame_rate if frame_rate else 0.0,
        },
        "rms": rms,
        "nonsilent": rms > 0,
    }


def _pcm_rms(data: bytes, sample_width: int) -> int:
    if not data:
        return 0
    if sample_width == 1:
        samples = (value - 128 for value in data)
    elif sample_width == 2:
        usable = data[: len(data) - (len(data) % 2)]
        samples = (item[0] for item in struct.iter_unpack("<h", usable))
    elif sample_width == 4:
        usable = data[: len(data) - (len(data) % 4)]
        samples = (item[0] for item in struct.iter_unpack("<i", usable))
    else:
        return 1 if any(data) else 0
    total = 0
    count = 0
    for sample in samples:
        total += sample * sample
        count += 1
    if count == 0:
        return 0
    return int((total / count) ** 0.5)
