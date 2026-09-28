"""In-process accepted Studio Engine render bridge."""

from __future__ import annotations

import hashlib
import importlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from harness.studio_body_contract import canonical_json
from harness.studio_body_engine_contract import EngineRenderStep
from harness.studio_body_engine_resolution import (
    StudioEngineRuntime,
    StudioEngineUnavailable,
    resolve_studio_engine_runtime,
    studio_engine_runtime_manifest,
)

ACCEPTED_ENGINE_HEAD = "81810e14c6902d3cb750c25c7c15d063ac723926"
_RAW_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class StudioEngineBridgeError(ValueError):
    pass


def render_studio_engine_world(step: EngineRenderStep) -> dict[str, Any]:
    runtime = _engine_runtime()
    root = runtime.root
    engine = _engine_module(runtime)
    frames, world = [], None
    try:
        for kind, obj in engine.run(
                seed=step.seed, generator=step.generator, max_steps=step.max_steps,
                target=step.target_score, floor=step.floor, scheme=step.scheme,
                corpus_path=None, render_frames=step.render_frames):
            if kind == "frame":
                frames.append(_frame(obj))
            elif kind == "world":
                world = obj.to_json()
    except Exception as exc:
        raise StudioEngineBridgeError(str(exc)) from exc
    if world is None or not frames:
        raise StudioEngineBridgeError("Studio Engine produced no visual frame")
    layer = world["layers"][0]
    return {
        "schema": "flywheel.studio.body.engine-render-receipt/v1",
        "engine_source": str(root),
        "engine_runtime": studio_engine_runtime_manifest(runtime),
        "engine_head": _git_head(root),
        "engine_head_expected": ACCEPTED_ENGINE_HEAD,
        "world_id": world["id"],
        "world_sha256": hashlib.sha256(canonical_json(world).encode()).hexdigest(),
        "world": world,
        "render_program": layer["render_program"],
        "audio_program": world.get("audio_program"),
        "engine_receipt": world["receipt"],
        "frame_count": len(frames),
        "frames": frames,
    }


def _engine_runtime() -> StudioEngineRuntime:
    try:
        return resolve_studio_engine_runtime()
    except StudioEngineUnavailable:
        raise


def _engine_module(runtime: StudioEngineRuntime):
    root = runtime.root
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)
    mod = importlib.import_module("studio_engine.engine")
    module_path = Path(getattr(mod, "__file__", "")).resolve()
    try:
        ok = module_path.is_relative_to(root)
    except ValueError:
        ok = False
    if not ok:
        raise StudioEngineBridgeError("loaded studio_engine module is outside resolved Studio Engine runtime")
    return mod


def _git_head(root: Path) -> str:
    try:
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True, timeout=5)
    except Exception:
        return "unknown"
    return proc.stdout.strip()


def _frame(value: dict[str, Any]) -> dict[str, Any]:
    receipt = value.get("delivery_receipt") if isinstance(value, dict) else None
    full = receipt.get("frame_sha256") if isinstance(receipt, dict) else None
    if not isinstance(full, str) or _RAW_SHA256.fullmatch(full) is None:
        raise StudioEngineBridgeError("Studio Engine frame lacks a full frame sha256")
    return {"frame": value["frame"], "t": value["t"], "sha256": value["sha256"],
            "frame_sha256": full, "png_base64": value["png_base64"],
            "delivery_receipt": receipt}
