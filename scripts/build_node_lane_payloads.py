"""Build owned Node/Learn/Telos payload trees from pinned source receipts."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from node_lane_payload_lib import (
    PayloadError,
    download,
    file_manifest,
    load_jsonl,
    reject_c_drive_source,
    safe_extract_tar,
    safe_extract_zip,
    sha256_file,
    verify_integrity,
    write_source_archive,
)

MANIFEST = Path("packaging/node-lane-payloads.jsonl")


def _row(rows: list[dict[str, Any]], lane: str) -> dict[str, Any]:
    for row in rows:
        if row.get("lane") == lane:
            return row
    raise PayloadError(f"missing lane: {lane}")


def _download_verified(url: str, cache_path: Path, sha256: str, skip: bool) -> Path:
    if skip:
        raise PayloadError(f"missing cached artifact with --skip-downloads: {cache_path}")
    if not cache_path.exists():
        download(url, cache_path)
    actual = "sha256:" + sha256_file(cache_path)
    if actual != sha256:
        raise PayloadError(f"artifact hash mismatch for {cache_path.name}: {actual}")
    return cache_path


def _copy_notices(out: Path, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    copied = []
    notice_dir = out / "notices"
    notice_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        for rel in row.get("notices", []):
            src = ROOT / rel
            if not src.exists():
                raise PayloadError(f"notice file missing: {rel}")
            dest = notice_dir / src.name
            shutil.copy2(src, dest)
            copied.append({"lane": row["lane"], "path": str(dest.relative_to(out)).replace("\\", "/")})
    return copied


def _signature_status(node_exe: Path) -> dict[str, Any]:
    ps = Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    executable = str(ps) if ps.exists() else "powershell"
    literal = str(node_exe).replace("'", "''")
    script = (
        f"$s=Get-AuthenticodeSignature -LiteralPath '{literal}'; "
        "$cert=$s.SignerCertificate; "
        "[pscustomobject]@{status=[string]$s.Status; signer=if($cert){$cert.Subject}else{$null}} | ConvertTo-Json -Compress"
    )
    env = dict(os.environ)
    env["PSModulePath"] = "C:/Windows/System32/WindowsPowerShell/v1.0/Modules"
    command = [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False, env=env)
    except Exception as exc:  # pragma: no cover - platform fallback
        return {"available": False, "error": str(exc)}
    if result.returncode != 0 or result.stderr.strip():
        return {"available": False, "error": result.stderr.strip() or result.stdout.strip()}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"available": False, "error": result.stdout.strip()}
    payload["available"] = True
    return payload

def _build_runtime(row: dict[str, Any], out: Path, cache: Path, skip: bool) -> dict[str, Any]:
    runtime = row["runtime"]
    archive = cache / "node" / Path(runtime["archive_url"]).name
    archive = _download_verified(runtime["archive_url"], archive, runtime["archive_sha256"], skip)
    dest = out / "components" / "node" / "v24.21.0-win-x64"
    if dest.exists():
        shutil.rmtree(dest)
    safe_extract_zip(archive, dest, strip_prefix="node-v24.21.0-win-x64")
    node_exe = dest / "node.exe"
    if not node_exe.exists():
        raise PayloadError("node.exe missing after extraction")
    return {
        "version": runtime["version"],
        "archive": str(archive),
        "archive_sha256": "sha256:" + sha256_file(archive),
        "node_exe_sha256": "sha256:" + sha256_file(node_exe),
        "signature": _signature_status(node_exe),
        "tree": file_manifest(dest),
    }


def _build_lane(row: dict[str, Any], source_root: Path, out: Path, cache: Path) -> dict[str, Any]:
    reject_c_drive_source(source_root)
    lane = row["lane"]
    source = row["source"]
    include_paths = source["bundle_paths"]
    archive = cache / "sources" / f"{lane}-{row['version']}-source.tar"
    archive_sha = "sha256:" + write_source_archive(source_root, include_paths, archive, source.get("exclude_paths", []))
    dest = out / "components" / "node-lanes" / f"{lane}-{row['version']}" / "package"
    if dest.exists():
        shutil.rmtree(dest)
    safe_extract_tar(archive, dest, strip_prefix="package")
    entry = dest / row["entrypoint"]["script"]
    if not entry.exists():
        raise PayloadError(f"{lane}: entrypoint missing after extraction")
    return {
        "lane": lane,
        "version": row["version"],
        "source_archive": str(archive),
        "source_archive_sha256": archive_sha,
        "entrypoint_sha256": "sha256:" + sha256_file(entry),
        "tree": file_manifest(dest),
        "server_info": row["entrypoint"]["server_info"],
        "allowed_tools": row["entrypoint"]["allowed_tools"],
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    rows = load_jsonl(Path(args.manifest))
    for candidate in (args.learn_source_root, args.telos_source_root):
        if candidate:
            reject_c_drive_source(Path(candidate))
    if args.skip_downloads:
        return {"schema": "flywheel.node-lane-payload-build-manifest/v1", "skipped": True}
    if not args.learn_source_root or not args.telos_source_root:
        raise PayloadError("learn-source-root and telos-source-root are required for source-delta payload builds")
    out = Path(args.out)
    cache = Path(args.cache)
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    runtime_receipt = _build_runtime(_row(rows, "learn"), out, cache, args.skip_downloads)
    lanes = [
        _build_lane(_row(rows, "learn"), Path(args.learn_source_root), out, cache),
        _build_lane(_row(rows, "telos"), Path(args.telos_source_root), out, cache),
    ]
    receipt = {
        "schema": "flywheel.node-lane-payload-build-manifest/v1",
        "runtime": runtime_receipt,
        "lanes": lanes,
        "notices": _copy_notices(out, rows),
        "launch_network_install": False,
        "lifecycle_scripts_run": False,
    }
    (out / "node-lane-payload-build-manifest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--out", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--learn-source-root")
    parser.add_argument("--telos-source-root")
    parser.add_argument("--skip-downloads", action="store_true")
    parser.add_argument("--extract-test-archive")
    args = parser.parse_args(argv)
    try:
        if args.extract_test_archive:
            safe_extract_tar(Path(args.extract_test_archive), Path(args.out) / "extract-test", strip_prefix="package")
            print(json.dumps({"verdict": "PASS"}, sort_keys=True))
            return 0
        print(json.dumps(build(args), sort_keys=True))
        return 0
    except PayloadError as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
