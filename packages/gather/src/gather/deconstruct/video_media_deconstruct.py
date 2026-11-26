"""Unified video, image, and daylight.sidecar/1 signal deconstructor (media-deconstruction/1)."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

from gather.deconstruct.audio_deconstruct import deconstruct_audio
from gather.deconstruct.paper_deconstruct import deconstruct_paper
from gather.engine_receipt import emit_gather_engine_receipt
from gather.saves_sidecar import find_links, parse_sidecar

MEDIA_SCHEMA = "media-deconstruction/1"
_AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
_VIDEO_EXT = {".mp4", ".mkv", ".mov", ".webm", ".avi"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp"}
_PAPER_EXT = {".pdf", ".html", ".htm", ".md", ".tex"}
_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", re.I)
_GH_URL_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", re.I)
_MEDIA_URL_RE = re.compile(r"\.(?:mp4|webm|mov|wav|mp3|flac|png|jpe?g|pdf)(?:\?|$)", re.I)


def probe_image_header(path: Path) -> dict[str, Any]:
    """Pure-Python header probe for PNG, JPEG, and BMP images."""
    raw = path.read_bytes()
    sha = "sha256:" + hashlib.sha256(raw).hexdigest()
    if raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) >= 26:
        w, h, bit_depth, color_type = struct.unpack(">IIBB", raw[16:26])
        return {"format": "png", "width": w, "height": h, "bit_depth": bit_depth,
                "color_type": color_type, "bytes": len(raw), "sha256": sha}
    if raw[:2] == b"\xff\xd8":
        idx = 2
        while idx + 4 < len(raw):
            if raw[idx] != 0xFF:
                break
            marker = raw[idx + 1]
            if marker in (0xC0, 0xC1, 0xC2) and idx + 9 < len(raw):
                precision, h, w = struct.unpack(">BHH", raw[idx + 4:idx + 9])
                return {"format": "jpeg", "width": w, "height": h, "bit_depth": precision,
                        "bytes": len(raw), "sha256": sha}
            seg_len = struct.unpack(">H", raw[idx + 2:idx + 4])[0]
            idx += 2 + seg_len
        return {"format": "jpeg", "width": 0, "height": 0, "bytes": len(raw), "sha256": sha}
    if raw[:2] == b"BM" and len(raw) >= 30:
        w, h, _planes, bpp = struct.unpack("<iiHH", raw[18:30])
        return {"format": "bmp", "width": abs(w), "height": abs(h), "bit_depth": bpp,
                "bytes": len(raw), "sha256": sha}
    return {"format": path.suffix.lstrip(".").lower() or "unknown", "width": 0, "height": 0,
            "bytes": len(raw), "sha256": sha}


def compute_motion_law_stats(frame_luminances: list[list[float]]) -> dict[str, Any]:
    """Compute frame-to-frame motion delta and scene-cut stats aligned with the 9 Motion Laws."""
    if len(frame_luminances) < 2:
        mean_lum = sum(frame_luminances[0]) / max(1, len(frame_luminances[0])) if frame_luminances else 0.0
        return {"frame_count": len(frame_luminances), "frame_deltas": [], "scene_cuts": [],
                "motion_energy_mean": 0.0, "motion_energy_peak": 0.0,
                "luminance_mean": round(mean_lum, 6), "motion_law_tags": ["static_still"]}
    deltas: list[float] = []
    for a, b in zip(frame_luminances, frame_luminances[1:]):
        n = min(len(a), len(b))
        d = sum(abs(x - y) for x, y in zip(a[:n], b[:n])) / max(1, n)
        deltas.append(round(d, 6))
    mean_d = sum(deltas) / len(deltas)
    peak_d = max(deltas)
    baseline = sorted(deltas)[len(deltas) // 2] if len(deltas) >= 3 else min(deltas)
    cut_thresh = max(0.25, baseline * 2.2)
    cuts = [i + 1 for i, d in enumerate(deltas) if d >= cut_thresh]
    mean_lum = sum(sum(f) / max(1, len(f)) for f in frame_luminances) / len(frame_luminances)
    tags = ["order_of_change"] if cuts else ["continuous_motion"]
    if peak_d < 0.03:
        tags.append("still_light_moving_weather")
    elif peak_d > 0.2:
        tags.append("burst_and_decay")
    return {
        "frame_count": len(frame_luminances),
        "frame_deltas": deltas,
        "scene_cuts": cuts,
        "motion_energy_mean": round(mean_d, 6),
        "motion_energy_peak": round(peak_d, 6),
        "luminance_mean": round(mean_lum, 6),
        "motion_law_tags": tags,
    }


def _probe_video(path: Path, out_dir: Path | None) -> dict[str, Any]:
    raw = path.read_bytes()
    sha = "sha256:" + hashlib.sha256(raw).hexdigest()
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe:
        return {
            "kind": "video", "source_path": path.name, "source_sha256": sha,
            "bytes": len(raw), "ffprobe_available": False, "ffmpeg_available": ffmpeg is not None,
            "motion": compute_motion_law_stats([]),
            "audio": None,
        }
    proc = subprocess.run(
        [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    info = json.loads(proc.stdout) if proc.returncode == 0 and proc.stdout.strip() else {}
    vstream: dict[str, Any] = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    audio_out = None
    if ffmpeg and out_dir is not None and any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
        wav_path = out_dir / f"{path.stem}_audio.wav"
        ext = subprocess.run(
            [ffmpeg, "-y", "-i", str(path), "-vn", "-acodec", "pcm_s16le", str(wav_path)],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if ext.returncode == 0 and wav_path.is_file():
            audio_out = deconstruct_audio(wav_path, out_dir=out_dir)
    return {
        "kind": "video", "source_path": path.name, "source_sha256": sha, "bytes": len(raw),
        "ffprobe_available": True, "ffmpeg_available": ffmpeg is not None,
        "codec": vstream.get("codec_name", ""),
        "width": int(vstream.get("width", 0) or 0),
        "height": int(vstream.get("height", 0) or 0),
        "duration_s": float((info.get("format") or {}).get("duration", 0.0) or 0.0),
        "motion": compute_motion_law_stats([]),
        "audio": audio_out,
    }


def deconstruct_sidecar_post(path: Path) -> dict[str, Any]:
    """Deconstruct a daylight.sidecar/1 Markdown post/thread into deduplicated claims and links."""
    raw = path.read_bytes()
    sc = parse_sidecar(str(path), raw)
    if sc is None:
        raise ValueError(f"not a daylight.sidecar/1 file: {path}")
    text = sc.text
    all_urls = sc.body_links + find_links(text)
    dedup_urls: dict[str, str] = {}
    for u in all_urls:
        dedup_urls.setdefault(hashlib.sha256(u.encode("utf-8")).hexdigest()[:16], u)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) >= 12]
    claims: list[dict[str, str]] = []
    seen_claims: set[str] = set()
    for s in sentences:
        h = "sha256:" + hashlib.sha256(s.lower().encode("utf-8")).hexdigest()
        if h not in seen_claims:
            seen_claims.add(h)
            claims.append({"claim_sha256": h, "text": s})
    urls = list(dedup_urls.values())
    return {
        "kind": "post_sidecar",
        "source_path": path.name,
        "source_sha256": "sha256:" + sc.sha256,
        "meta": sc.meta,
        "workflow_hints": sc.meta.get("workflow_hints") or [],
        "claims": claims,
        "urls": urls,
        "arxiv_ids": sorted({m.group(1) for u in urls for m in [_ARXIV_URL_RE.search(u)] if m}),
        "github_repos": sorted({m.group(1).rstrip("/") for u in urls for m in [_GH_URL_RE.search(u)] if m}),
        "media_targets": [u for u in urls if _MEDIA_URL_RE.search(u)],
        "problems": sc.problems,
    }


def _classify_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _AUDIO_EXT:
        return "audio"
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _IMAGE_EXT:
        return "image"
    if ext == ".md":
        head = path.read_bytes()[:512]
        if b"daylight.sidecar/1" in head:
            return "post_sidecar"
        return "whitepaper"
    if ext in _PAPER_EXT:
        return "whitepaper"
    return "unknown"


def deconstruct_artifact(
    path: Path, out_dir: Path | None = None, *, hmac_key: str | None = None
) -> dict[str, Any]:
    """Unified dispatcher for whitepaper, audio, video, image, and daylight.sidecar/1 artifacts."""
    kind = _classify_path(path)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    if kind == "whitepaper":
        payload = deconstruct_paper(path)
    elif kind == "audio":
        payload = deconstruct_audio(path, out_dir=out_dir)
    elif kind == "video":
        payload = _probe_video(path, out_dir)
    elif kind == "image":
        payload = {"kind": "image", "header": probe_image_header(path), "motion": compute_motion_law_stats([[0.5]])}
    elif kind == "post_sidecar":
        payload = deconstruct_sidecar_post(path)
    else:
        raise ValueError(f"unsupported artifact kind for {path.name}")
    manifest: dict[str, Any] = {"schema": MEDIA_SCHEMA, "artifact_kind": kind, "source_path": path.name, "payload": payload}
    artifacts: list[Path] = [path]
    if out_dir is not None:
        mpath = out_dir / "media_deconstruction.json"
        mpath.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        artifacts.extend([mpath, *sorted(out_dir.glob("stem_*.wav"))])
    ok_status = payload.get("status", "OK") not in ("DRIFT", "UNVERIFIABLE")
    receipt = emit_gather_engine_receipt(
        f"deconstruct-{kind}-{path.stem}", out_dir or path.parent, artifacts,
        verified=True if ok_status else (None if payload.get("status") == "UNVERIFIABLE" else False),
        pass_count=1 if ok_status else 0, fail_count=0 if ok_status else 1,
        command=["gather", "deconstruct", path.name],
        summary=f"[PASS] deconstruct {kind} {path.name}" if ok_status else f"FAIL: {payload.get('reason', 'error')}",
        hmac_key=hmac_key,
    )
    if out_dir is not None:
        (out_dir / "engine_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["receipt"] = receipt
    return manifest
