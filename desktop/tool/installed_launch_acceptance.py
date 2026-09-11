"""CLI facade for the Flywheel installed-launch acceptance harness."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

try:
    from .installed_launch_acceptance_model import (
        APP_ID, ASSERTION_IDS, PHASE_ASSERTIONS, PHASE_IDS, SCHEMA,
        FixedClock, HarnessConfig, LocalFilesystem, MetadataResult,
        NullHttpClient, NullProcessController, NullWindowsMetadata,
        ProcessHandle, ReceiptError, ShortcutRecord, assertion_state,
        default_commit, default_version, display_path, sha256_file,
        sha256_text, verify_receipt_file,
    )
    from .installed_launch_acceptance_platform import (
        LocalHttpClient, LocalProcessController, LocalWindowsMetadata,
    )
    from .installed_launch_acceptance_runner import AcceptanceHarness
except ImportError:
    from installed_launch_acceptance_model import (  # type: ignore
        APP_ID, ASSERTION_IDS, PHASE_ASSERTIONS, PHASE_IDS, SCHEMA,
        FixedClock, HarnessConfig, LocalFilesystem, MetadataResult,
        NullHttpClient, NullProcessController, NullWindowsMetadata,
        ProcessHandle, ReceiptError, ShortcutRecord, assertion_state,
        default_commit, default_version, display_path, sha256_file,
        sha256_text, verify_receipt_file,
    )
    from installed_launch_acceptance_platform import (  # type: ignore
        LocalHttpClient, LocalProcessController, LocalWindowsMetadata,
    )
    from installed_launch_acceptance_runner import AcceptanceHarness  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--mode", default="preflight")
    parser.add_argument("--start-engine", action="store_true")
    parser.add_argument("--include-local-paths", action="store_true")
    parser.add_argument("--artifact-root")
    parser.add_argument("--source-commit-expected", default=default_commit(_repo_root()))
    parser.add_argument("--expected-version", default=default_version(_repo_root() / "desktop" / "pubspec.yaml"))
    parser.add_argument("--expected-api-version", type=int, default=1)
    parser.add_argument("--expected-app-sha256", default="")
    parser.add_argument("--expected-engine-sha256", default="")
    parser.add_argument("--build-manifest")
    parser.add_argument("--expect-installer-payload", action="store_true")
    parser.add_argument("--require-desktop-shortcut", action="store_true")
    parser.add_argument("--before-receipt")
    parser.add_argument("--after-receipt")
    parser.add_argument("--port", type=int, default=0)
    return parser


def config_from_args(args) -> HarnessConfig:
    run_id = args.run_id or "installed_launch_" + uuid.uuid4().hex
    return HarnessConfig(
        install_root=Path(args.install_root),
        out=Path(args.out),
        run_id=run_id,
        mode=args.mode,
        start_engine=args.start_engine,
        include_local_paths=args.include_local_paths,
        artifact_root=Path(args.artifact_root) if args.artifact_root else None,
        source_commit_expected=args.source_commit_expected,
        expected_version=args.expected_version,
        expected_api_version=args.expected_api_version,
        expected_app_sha256=args.expected_app_sha256,
        expected_engine_sha256=args.expected_engine_sha256,
        build_manifest=Path(args.build_manifest) if args.build_manifest else None,
        expect_installer_payload=args.expect_installer_payload,
        require_desktop_shortcut=args.require_desktop_shortcut,
        before_receipt=Path(args.before_receipt) if args.before_receipt else None,
        after_receipt=Path(args.after_receipt) if args.after_receipt else None,
        port=args.port,
    )


def main(argv: list[str] | None = None) -> int:
    cfg = config_from_args(build_parser().parse_args(argv))
    receipt = AcceptanceHarness(
        cfg,
        fs=LocalFilesystem(),
        windows=LocalWindowsMetadata(),
        http=LocalHttpClient(),
        process=LocalProcessController(),
    ).run()
    print(json.dumps({"schema": SCHEMA + "-summary", "run_id": receipt["run_id"],
                      "complete": receipt["complete"],
                      "out": display_path(cfg.out, cfg.install_root,
                                          cfg.include_local_paths)}))
    return 0 if receipt["complete"] else 1


__all__ = [
    "APP_ID", "ASSERTION_IDS", "PHASE_ASSERTIONS", "PHASE_IDS", "SCHEMA",
    "AcceptanceHarness", "FixedClock", "HarnessConfig", "LocalFilesystem", "MetadataResult", "NullHttpClient",
    "NullProcessController", "NullWindowsMetadata", "ProcessHandle",
    "ReceiptError", "ShortcutRecord", "assertion_state", "main",
    "sha256_file", "sha256_text", "verify_receipt_file",
]


if __name__ == "__main__":
    sys.exit(main())
