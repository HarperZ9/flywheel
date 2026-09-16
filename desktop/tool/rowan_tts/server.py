from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .engines import (
    FakeWavEngine,
    QwenBaseVoiceCloneEngine,
    QwenVoiceDesignEngine,
    load_base_voice_profiles,
)
from .http_server import make_server
from .jobs import RowanTtsState
from .provenance import (
    DEFAULT_MODEL_REPO,
    DEFAULT_MODEL_REVISION,
    DEFAULT_BASE_MODEL_REPO,
    DEFAULT_BASE_MODEL_REVISION,
    DEFAULT_VOICE_PROMPT,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the private Rowan local TTS service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8798)
    parser.add_argument("--backend", choices=["qwen", "qwen-base", "fake"], default="qwen")
    parser.add_argument("--token", default=os.environ.get("ROWAN_LOCAL_TTS_TOKEN"))
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--model-dir")
    parser.add_argument("--repo-id")
    parser.add_argument("--revision")
    parser.add_argument("--profile-config")
    parser.add_argument("--hf-home", default=os.environ.get("HF_HOME"))
    parser.add_argument("--hf-hub-cache", default=os.environ.get("HF_HUB_CACHE"))
    parser.add_argument("--fake-delay-s", type=float, default=0.0)
    parser.add_argument("--max-profiles", type=int, default=1)
    parser.add_argument("--max-prompt-cache", type=int, default=1)
    parser.add_argument("--max-queue", type=int, default=1)
    parser.add_argument("--max-text-chars", type=int, default=1000)
    parser.add_argument("--print-ready", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.token:
        raise SystemExit("ROWAN_LOCAL_TTS_TOKEN or --token is required")
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.backend == "fake":
        engine = FakeWavEngine(delay_s=max(args.fake_delay_s, 0.0))
    elif args.backend == "qwen":
        if not args.model_dir:
            raise SystemExit("--model-dir is required for --backend qwen")
        engine = QwenVoiceDesignEngine(
            model_dir=Path(args.model_dir).resolve(),
            repo_id=args.repo_id or DEFAULT_MODEL_REPO,
            revision=args.revision or DEFAULT_MODEL_REVISION,
            hf_home=args.hf_home,
            hf_hub_cache=args.hf_hub_cache,
        )
    else:
        if not args.model_dir:
            raise SystemExit("--model-dir is required for --backend qwen-base")
        if not args.profile_config:
            raise SystemExit("--profile-config is required for --backend qwen-base")
        profiles = load_base_voice_profiles(
            Path(args.profile_config).resolve(),
            max_profiles=args.max_profiles,
        )
        engine = QwenBaseVoiceCloneEngine(
            model_dir=Path(args.model_dir).resolve(),
            profiles=profiles,
            repo_id=args.repo_id or DEFAULT_BASE_MODEL_REPO,
            revision=args.revision or DEFAULT_BASE_MODEL_REVISION,
            hf_home=args.hf_home,
            hf_hub_cache=args.hf_hub_cache,
            max_prompt_cache=args.max_prompt_cache,
        )
    state = RowanTtsState(
        engine=engine,
        out_dir=out_dir,
        token=args.token,
        max_queue=max(args.max_queue, 1),
        max_text_chars=max(args.max_text_chars, 1),
    )
    server = make_server(args.host, args.port, state)
    if args.print_ready:
        print(
            json.dumps(
                {
                    "schema": "rowan.local-tts-ready/v1",
                    "host": args.host,
                    "port": args.port,
                    "backend": args.backend,
                    "out_dir": str(out_dir),
                    "voice_prompt_default_sha256_only": True,
                    "voice_prompt_supported": bool(getattr(engine, "allow_voice_prompt", True)),
                    "voice_prompt_len": len(getattr(engine, "default_voice_prompt", DEFAULT_VOICE_PROMPT)),
                    "profile_count": len(getattr(engine, "profiles", {})),
                    "max_prompt_cache": getattr(engine, "max_prompt_cache", None),
                }
            ),
            flush=True,
        )
    try:
        server.serve_forever()
    finally:
        state.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
