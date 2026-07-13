"""Emit metadata-only readiness receipts for gather/source intake.

This command checks static gather adapter/config surfaces and credential
presence booleans only. It does not read config bodies, run gather, scrape
sources, call Discord, or print credential values.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


CORE_SURFACES = [
    "README.md",
    "src/gather",
    "tests",
]

DISCORD_SURFACES = [
    "src/gather/discord.py",
    "src/gather/run_config.py",
    "src/gather/method.py",
    "tests/test_discord.py",
]


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_paths(value: str) -> list[Path]:
    return [Path(item.strip()) for item in value.split(";") if item.strip()]


def split_names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _surface(root: Path, rels: list[str]) -> dict[str, Any]:
    present = [rel for rel in rels if (root / rel).exists()]
    missing = [rel for rel in rels if rel not in present]
    total = len(rels)
    return {
        "required": total,
        "present": len(present),
        "missing": len(missing),
        "score": round(len(present) / total, 4) if total else 1.0,
        "present_files": present,
        "missing_files": missing,
    }


def _config_rows(config_roots: list[Path], *, pattern: str, max_configs: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in config_roots:
        if not root.exists() or not root.is_dir():
            continue
        try:
            matches = sorted(root.glob(pattern), key=lambda p: p.name.lower())
        except OSError:
            continue
        for path in matches:
            if len(rows) >= max_configs:
                return rows
            if not path.is_file():
                continue
            rows.append({
                "path": str(path),
                "name": path.name,
                "suffix": path.suffix.lower(),
                "size_bytes": _safe_size(path),
                "content_read": False,
            })
    return rows


def _credentials(vars_: list[str]) -> dict[str, bool]:
    return {name: bool(os.environ.get(name)) for name in vars_}


def _verdict(*, root_exists: bool, core_score: float, discord_score: float, config_count: int, credential_present: bool) -> str:
    if not root_exists:
        return "GATHER_MISSING"
    if core_score < 1.0 or discord_score < 1.0 or config_count <= 0:
        return "GATHER_STATIC_PARTIAL"
    if credential_present:
        return "GATHER_STATIC_READY_WITH_CREDENTIAL"
    return "GATHER_STATIC_READY_NEEDS_CREDENTIAL"


def profile_gather(
    *,
    gather_root: Path,
    config_roots: list[Path],
    config_pattern: str,
    credential_vars: list[str],
    max_configs: int,
) -> dict[str, Any]:
    gather_root = gather_root.expanduser()
    root_exists = gather_root.exists()
    core = _surface(gather_root, CORE_SURFACES) if root_exists else _surface(Path("__missing__"), CORE_SURFACES)
    discord = _surface(gather_root, DISCORD_SURFACES) if root_exists else _surface(Path("__missing__"), DISCORD_SURFACES)
    configs = _config_rows(config_roots, pattern=config_pattern, max_configs=max_configs)
    credentials = _credentials(credential_vars)
    credential_present = any(credentials.values())
    verdict = _verdict(
        root_exists=root_exists,
        core_score=float(core["score"]),
        discord_score=float(discord["score"]),
        config_count=len(configs),
        credential_present=credential_present,
    )
    return {
        "schema": "harness.gather-readiness.profile/v1",
        "root": str(gather_root),
        "root_exists": root_exists,
        "content_read": False,
        "surfaces": {
            "core": core,
            "discord": discord,
        },
        "config_roots": [str(path) for path in config_roots],
        "config_pattern": config_pattern,
        "config_count": len(configs),
        "configs": configs,
        "credentials": credentials,
        "credential_present": credential_present,
        "verdict": verdict,
    }


def build_report(
    *,
    gather_root: Path,
    config_roots: list[Path],
    config_pattern: str,
    credential_vars: list[str],
    max_configs: int,
) -> dict[str, Any]:
    profile = profile_gather(
        gather_root=gather_root,
        config_roots=config_roots,
        config_pattern=config_pattern,
        credential_vars=credential_vars,
        max_configs=max_configs,
    )
    return {
        "schema": "harness.gather-readiness/v1",
        "timestamp_utc": now_utc(),
        "secret_policy": "metadata-only; credentials are booleans only; config bodies are not read; live capture is not attempted",
        "profile": profile,
        "summary": {
            "root_exists": profile["root_exists"],
            "config_count": profile["config_count"],
            "credential_present": profile["credential_present"],
            "core_score": profile["surfaces"]["core"]["score"],
            "discord_score": profile["surfaces"]["discord"]["score"],
            "verdict": profile["verdict"],
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    profile = report["profile"]
    lines = [
        "# Gather readiness receipt",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Timestamp UTC: `{report['timestamp_utc']}`",
        f"- Secret policy: {report['secret_policy']}",
        f"- Gather root: `{profile['root']}`",
        f"- Root exists: `{str(summary['root_exists']).lower()}`",
        f"- Config count: `{summary['config_count']}`",
        f"- Credential present: `{str(summary['credential_present']).lower()}`",
        f"- Verdict: `{summary['verdict']}`",
        "",
        "| Surface | Score | Present | Missing |",
        "|---|---:|---:|---:|",
    ]
    for name, row in profile["surfaces"].items():
        lines.append(
            f"| {name} | {row['score']} | {row['present']} | {row['missing']} |"
        )
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _store_outputs(report: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="gather_readiness",
            body=report,
            run_id=run_id,
            verdict=report["summary"]["verdict"],
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gather-root", default="C:/dev/public/gather")
    parser.add_argument("--config-roots", default="C:/dev/local-model/configs")
    parser.add_argument("--config-pattern", default="gather-*.json")
    parser.add_argument("--credential-vars", default="GATHER_DISCORD_BOT_TOKEN,DISCORD_TOKEN")
    parser.add_argument("--max-configs", type=int, default=100)
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    report = build_report(
        gather_root=Path(args.gather_root),
        config_roots=split_paths(args.config_roots),
        config_pattern=args.config_pattern,
        credential_vars=split_names(args.credential_vars),
        max_configs=args.max_configs,
    )
    json_text = json.dumps(report, indent=2, sort_keys=True)
    md_text = render_markdown(report)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = _store_outputs(
        report,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "gather-readiness-json"),
            (md_path, "gather-readiness-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
