from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .provenance import (
    DEFAULT_GENERATION,
    DEFAULT_MODEL_REPO,
    DEFAULT_MODEL_REVISION,
    DEFAULT_PROFILE,
    DEFAULT_VOICE_PROMPT,
    gpu_snapshot,
    ram_snapshot,
    reject_source_tokens,
    sanitize_generation,
    sha256_text,
    utc_now,
    wav_info,
    write_json,
)


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def body(self) -> dict[str, Any]:
        return {
            "schema": "rowan.local-tts-error/v1",
            "ok": False,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class TtsJob:
    job_id: str
    text: str
    voice_prompt: str
    profile: str
    generation: dict[str, Any]
    seed: int
    out_dir: Path
    created_utc: str = field(default_factory=utc_now)
    state: str = "queued"
    cancel_requested: bool = False
    started_utc: str | None = None
    finished_utc: str | None = None
    error: str | None = None
    output_path: Path | None = None
    manifest_path: Path | None = None
    elapsed_s: float | None = None
    engine_meta: dict[str, Any] | None = None
    gpu_before: dict[str, Any] | None = None
    gpu_after: dict[str, Any] | None = None
    ram_before: dict[str, Any] | None = None
    ram_after: dict[str, Any] | None = None
    condition: threading.Condition = field(default_factory=threading.Condition)

    @property
    def terminal(self) -> bool:
        return self.state in {"completed", "cancelled", "failed"}

    def public_summary(self) -> dict[str, Any]:
        return {
            "schema": "rowan.local-tts-job/v1",
            "job_id": self.job_id,
            "state": self.state,
            "profile": self.profile,
            "text_sha256": sha256_text(self.text),
            "voice_prompt_sha256": sha256_text(self.voice_prompt),
            "seed": self.seed,
            "created_utc": self.created_utc,
            "started_utc": self.started_utc,
            "finished_utc": self.finished_utc,
            "cancel_requested": self.cancel_requested,
            "elapsed_s": self.elapsed_s,
            "error": self.error,
            "audio_path": str(self.output_path) if self.output_path else None,
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
        }


class RowanTtsState:
    def __init__(
        self,
        *,
        engine: Any,
        out_dir: Path,
        token: str,
        max_queue: int = 1,
        max_text_chars: int = 1000,
    ) -> None:
        if not token:
            raise ValueError("token is required")
        self.engine = engine
        self.out_dir = out_dir
        self.token = token
        self.max_queue = max_queue
        self.max_text_chars = max_text_chars
        self.accepting = True
        self._jobs: dict[str, TtsJob] = {}
        self._active: str | None = None
        self._stop_requested = False
        self._lock = threading.Lock()
        self._queue: queue.Queue[TtsJob | None] = queue.Queue(max_queue)
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def submit(self, payload: dict[str, Any]) -> TtsJob:
        self._raise_if_stopping()
        text = _string_field(payload, "text")
        if not text.strip():
            raise ServiceError(400, "EMPTY_TEXT", "text is required")
        if len(text) > self.max_text_chars:
            raise ServiceError(413, "TEXT_TOO_LARGE", "text exceeds limit")
        voice_prompt = payload.get("voice_prompt") or DEFAULT_VOICE_PROMPT
        if not isinstance(voice_prompt, str):
            raise ServiceError(400, "BAD_VOICE_PROMPT", "voice_prompt must be a string")
        profile = payload.get("profile") or DEFAULT_PROFILE
        if not isinstance(profile, str):
            raise ServiceError(400, "BAD_PROFILE", "profile must be a string")
        try:
            reject_source_tokens("text", text)
            reject_source_tokens("voice_prompt", voice_prompt)
            generation = sanitize_generation(payload.get("generation"))
        except ValueError as exc:
            raise ServiceError(400, "BAD_REQUEST", str(exc)) from exc
        seed = payload.get("seed")
        if seed is None:
            seed = int(time.time() * 1000) % 2147483647
        if not isinstance(seed, int):
            raise ServiceError(400, "BAD_SEED", "seed must be an integer")
        job = TtsJob(
            job_id=f"tts_{uuid.uuid4().hex}",
            text=text,
            voice_prompt=voice_prompt,
            profile=profile,
            generation=generation,
            seed=seed,
            out_dir=self.out_dir,
        )
        with self._lock:
            if self._stop_requested or not self.accepting:
                raise ServiceError(503, "SERVICE_STOPPING", "service is stopping")
            self._jobs[job.job_id] = job
            try:
                self._queue.put_nowait(job)
            except queue.Full as exc:
                self._jobs.pop(job.job_id, None)
                raise ServiceError(429, "QUEUE_FULL", "synthesis queue is full") from exc
        return job

    def _raise_if_stopping(self) -> None:
        with self._lock:
            if self._stop_requested or not self.accepting:
                raise ServiceError(503, "SERVICE_STOPPING", "service is stopping")

    def get(self, job_id: str) -> TtsJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise ServiceError(404, "JOB_NOT_FOUND", "job was not found")
        return job

    def cancel(self, job_id: str) -> TtsJob:
        job = self.get(job_id)
        with job.condition:
            job.cancel_requested = True
            if job.state == "queued":
                job.state = "cancelled"
                job.finished_utc = utc_now()
                job.elapsed_s = 0.0
                self._write_manifest(job, reason="cancelled_while_queued")
            job.condition.notify_all()
        return job

    def wait(self, job: TtsJob, timeout_s: float) -> TtsJob:
        deadline = time.monotonic() + timeout_s
        with job.condition:
            while not job.terminal:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                job.condition.wait(min(remaining, 0.25))
        return job

    def health(self) -> dict[str, Any]:
        with self._lock:
            active = self._active
            jobs = len(self._jobs)
            stop_requested = self._stop_requested
        return {
            "schema": "rowan.local-tts-health/v1",
            "ok": True,
            "backend": getattr(self.engine, "backend", "unknown"),
            "accepting": self.accepting,
            "max_queue": self.max_queue,
            "max_text_chars": self.max_text_chars,
            "active_job_id": active,
            "known_jobs": jobs,
            "model_resident": bool(getattr(self.engine, "resident", False)),
            "stop_requested": stop_requested,
        }

    def stop(self) -> None:
        with self._lock:
            if self._stop_requested:
                return
            self.accepting = False
            self._stop_requested = True
            queued = [job for job in self._jobs.values() if job.state == "queued"]
        for job in queued:
            with job.condition:
                if job.state == "queued":
                    job.cancel_requested = True
                    job.state = "cancelled"
                    job.finished_utc = utc_now()
                    job.elapsed_s = 0.0
                    self._write_manifest(job, reason="service_stopping")
                job.condition.notify_all()
        threading.Thread(target=self._enqueue_stop, daemon=True).start()

    def _enqueue_stop(self) -> None:
        self._queue.put(None)

    def _worker_loop(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                self._queue.task_done()
                break
            try:
                self._run_job(job)
            finally:
                self._queue.task_done()

    def _run_job(self, job: TtsJob) -> None:
        with job.condition:
            if job.state == "cancelled":
                job.condition.notify_all()
                return
            job.state = "running"
            job.started_utc = utc_now()
            job.condition.notify_all()
        with self._lock:
            self._active = job.job_id
        start = time.perf_counter()
        try:
            job.gpu_before = gpu_snapshot()
            job.ram_before = ram_snapshot()
            output = job.out_dir / job.job_id / "audio.wav"
            job.engine_meta = self.engine.synthesize(
                text=job.text,
                voice_prompt=job.voice_prompt,
                seed=job.seed,
                generation=job.generation,
                output_path=output,
            )
            job.output_path = output
            job.elapsed_s = time.perf_counter() - start
            job.gpu_after = gpu_snapshot()
            job.ram_after = ram_snapshot()
            with job.condition:
                job.state = "completed"
                job.finished_utc = utc_now()
                self._write_manifest(job)
                job.condition.notify_all()
        except Exception as exc:
            with job.condition:
                job.state = "failed"
                job.error = repr(exc)
                job.elapsed_s = time.perf_counter() - start
                job.finished_utc = utc_now()
                self._write_manifest(job)
                job.condition.notify_all()
        finally:
            with self._lock:
                if self._active == job.job_id:
                    self._active = None

    def _write_manifest(self, job: TtsJob, reason: str | None = None) -> None:
        path = job.out_dir / job.job_id / "manifest.json"
        job.manifest_path = path
        payload = {
            "schema": "rowan.local-tts-job-manifest/v1",
            "job": job.public_summary(),
            "reason": reason,
            "text": job.text,
            "voice_prompt": job.voice_prompt,
            "generation": job.generation,
            "model": job.engine_meta
            or {
                "repo_id": DEFAULT_MODEL_REPO,
                "revision": DEFAULT_MODEL_REVISION,
            },
            "gpu_before": job.gpu_before,
            "gpu_after": job.gpu_after,
            "ram_before": job.ram_before,
            "ram_after": job.ram_after,
            "wav": wav_info(job.output_path) if job.output_path else None,
            "boundary": "full-buffer WAV generation; not streaming or real-time speech",
        }
        write_json(path, payload)


def _string_field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ServiceError(400, f"BAD_{key.upper()}", f"{key} must be a string")
    return value
