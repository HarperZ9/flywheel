from __future__ import annotations

import gc
import math
import os
import struct
import time
import wave
from pathlib import Path
from typing import Any

from .base_profiles import BaseVoiceProfile
from .provenance import (
    DEFAULT_BASE_MODEL_REPO,
    DEFAULT_BASE_MODEL_REVISION,
    sha256_text,
    verify_model_dir_identity,
)


class PromptCacheMixin:
    allow_voice_prompt = False
    default_voice_prompt = ""

    def __init__(self, *, profiles: dict[str, BaseVoiceProfile], max_prompt_cache: int = 1) -> None:
        if not profiles:
            raise ValueError("at least one Base voice profile is required")
        if max_prompt_cache < 1 or max_prompt_cache > len(profiles):
            raise ValueError("max_prompt_cache must be between 1 and the profile count")
        self.profiles = dict(profiles)
        self.max_prompt_cache = max_prompt_cache
        self._prompt_cache: dict[str, Any] = {}

    @property
    def prompt_cache_size(self) -> int:
        return len(self._prompt_cache)

    def validate_profile(self, profile: str) -> None:
        if profile not in self.profiles:
            raise ValueError("profile is not in the configured Base profile set")

    def _profile(self, profile: str) -> BaseVoiceProfile:
        self.validate_profile(profile)
        return self.profiles[profile]

    def _cache_profile(self, profile: str, value_factory: Any) -> tuple[Any, bool]:
        if profile in self._prompt_cache:
            return self._prompt_cache[profile], True
        if len(self._prompt_cache) >= self.max_prompt_cache:
            raise RuntimeError("prompt cache limit exceeded")
        value = value_factory()
        self._prompt_cache[profile] = value
        return value, False

    def _profile_meta(self, profile: BaseVoiceProfile) -> dict[str, Any]:
        return profile.manifest()


class FakeBasePromptEngine(PromptCacheMixin):
    """Fast deterministic Base-style backend for profile/cache contract tests."""

    backend = "fake-base-profile-cache"

    def __init__(
        self,
        *,
        profiles: dict[str, BaseVoiceProfile],
        max_prompt_cache: int = 1,
        delay_s: float = 0.0,
    ) -> None:
        super().__init__(profiles=profiles, max_prompt_cache=max_prompt_cache)
        self.delay_s = delay_s
        self.load_calls = 0
        self.synth_calls = 0

    @property
    def resident(self) -> bool:
        return self.load_calls > 0

    def load(self) -> dict[str, Any]:
        self.load_calls += 1
        return {"backend": self.backend, "elapsed_s": 0.0, "resident": True}

    def synthesize(
        self,
        *,
        text: str,
        voice_prompt: str,
        profile: str,
        seed: int,
        generation: dict[str, Any],
        output_path: Path,
    ) -> dict[str, Any]:
        load_meta = self.load()
        base_profile = self._profile(profile)
        _, cache_hit = self._cache_profile(profile, lambda: {"built_at": time.time()})
        self.synth_calls += 1
        if self.delay_s:
            time.sleep(self.delay_s)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 24000
        frames = int(sample_rate * max(0.25, min(1.0, len(text) / 120.0)))
        phase = seed % sample_rate
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            for i in range(frames):
                sample = int(9000 * math.sin((i + phase) * 2 * math.pi * 220 / sample_rate))
                wav.writeframes(struct.pack("<h", sample))
        return {
            "backend": self.backend,
            "engine": "fake-base-profile-cache",
            "sample_rate": sample_rate,
            "load": load_meta,
            "profile": self._profile_meta(base_profile),
            "prompt_cache_hit": cache_hit,
            "prompt_cache_size": self.prompt_cache_size,
            "prompt_cache_limit": self.max_prompt_cache,
            "voice_prompt_used": False,
        }


class QwenBaseVoiceCloneEngine(PromptCacheMixin):
    """Lazy local Qwen3-TTS Base backend with bounded profile prompt cache."""

    backend = "qwen3-tts-base-voice-clone"

    def __init__(
        self,
        *,
        model_dir: Path,
        profiles: dict[str, BaseVoiceProfile],
        repo_id: str = DEFAULT_BASE_MODEL_REPO,
        revision: str = DEFAULT_BASE_MODEL_REVISION,
        hf_home: str | None = None,
        hf_hub_cache: str | None = None,
        max_prompt_cache: int = 1,
    ) -> None:
        super().__init__(profiles=profiles, max_prompt_cache=max_prompt_cache)
        self.model_dir = model_dir
        self.repo_id = repo_id
        self.revision = revision
        self.hf_home = hf_home
        self.hf_hub_cache = hf_hub_cache
        self._model: Any | None = None
        self._torch: Any | None = None
        self._np: Any | None = None
        self._sf: Any | None = None
        self._attn: str | None = None
        self._load_elapsed_s: float | None = None
        self._artifact_identity: dict[str, Any] | None = None

    @property
    def resident(self) -> bool:
        return self._model is not None

    def _offline_env(self) -> None:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        if self.hf_home:
            os.environ["HF_HOME"] = self.hf_home
        if self.hf_hub_cache:
            os.environ["HF_HUB_CACHE"] = self.hf_hub_cache

    def load(self) -> dict[str, Any]:
        if self._model is not None:
            return {
                "backend": self.backend,
                "elapsed_s": 0.0,
                "resident": True,
                "attn_implementation": self._attn,
                "previous_load_elapsed_s": self._load_elapsed_s,
                "artifact_identity": self._artifact_identity,
            }
        if not self.model_dir.exists():
            raise RuntimeError(f"model_dir not found: {self.model_dir}")
        self._offline_env()
        self._artifact_identity = verify_model_dir_identity(
            self.model_dir,
            self.revision,
            repo_id=self.repo_id,
            tts_model_type="base",
        )
        import numpy as np
        import soundfile as sf
        import torch
        from qwen_tts import Qwen3TTSModel

        errors: dict[str, str] = {}
        for attn in ("sdpa", "eager"):
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            start = time.perf_counter()
            try:
                self._model = Qwen3TTSModel.from_pretrained(
                    str(self.model_dir),
                    local_files_only=True,
                    device_map="cuda:0",
                    dtype=torch.bfloat16,
                    attn_implementation=attn,
                )
                self._torch = torch
                self._np = np
                self._sf = sf
                self._attn = attn
                self._load_elapsed_s = time.perf_counter() - start
                return {
                    "backend": self.backend,
                    "elapsed_s": self._load_elapsed_s,
                    "resident": True,
                    "attn_implementation": attn,
                    "repo_id": self.repo_id,
                    "revision": self.revision,
                    "model_dir": str(self.model_dir),
                    "artifact_identity": self._artifact_identity,
                }
            except Exception as exc:
                errors[attn] = repr(exc)
        raise RuntimeError(f"qwen base load failed: {errors}")

    def synthesize(
        self,
        *,
        text: str,
        voice_prompt: str,
        profile: str,
        seed: int,
        generation: dict[str, Any],
        output_path: Path,
    ) -> dict[str, Any]:
        load_meta = self.load()
        assert self._model is not None
        assert self._torch is not None
        assert self._np is not None
        assert self._sf is not None
        base_profile = self._profile(profile)
        prompt_start = time.perf_counter()
        prompt_items, cache_hit = self._cache_profile(
            profile,
            lambda: self._model.create_voice_clone_prompt(
                ref_audio=str(base_profile.reference_audio_path),
                ref_text=base_profile.reference_text,
                x_vector_only_mode=base_profile.x_vector_only_mode,
            ),
        )
        prompt_elapsed = 0.0 if cache_hit else time.perf_counter() - prompt_start
        self._torch.manual_seed(seed)
        if self._torch.cuda.is_available():
            self._torch.cuda.manual_seed_all(seed)
            self._torch.cuda.reset_peak_memory_stats()
        synth_start = time.perf_counter()
        wavs, sample_rate = self._model.generate_voice_clone(
            text=text,
            language="English",
            voice_clone_prompt=prompt_items,
            non_streaming_mode=True,
            **generation,
        )
        synthesis_elapsed = time.perf_counter() - synth_start
        wav = self._np.asarray(wavs[0], dtype=self._np.float32)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._sf.write(output_path, wav, int(sample_rate))
        peak = None
        if self._torch.cuda.is_available():
            peak = round(self._torch.cuda.max_memory_allocated() / 1048576, 3)
        return {
            "backend": self.backend,
            "engine": "qwen_tts.Qwen3TTSModel.generate_voice_clone",
            "repo_id": self.repo_id,
            "revision": self.revision,
            "model_dir": str(self.model_dir),
            "attn_implementation": self._attn,
            "load": load_meta,
            "profile": self._profile_meta(base_profile),
            "prompt_cache_hit": cache_hit,
            "prompt_cache_size": self.prompt_cache_size,
            "prompt_cache_limit": self.max_prompt_cache,
            "prompt_build_elapsed_s": prompt_elapsed,
            "synthesis_elapsed_s": synthesis_elapsed,
            "voice_prompt_used": False,
            "sample_rate": int(sample_rate),
            "torch_peak_allocated_mb": peak,
            "text_sha256": sha256_text(text),
        }
