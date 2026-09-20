"""Stage manifest-pinned Python lane source checkouts for frozen builds."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "packaging" / "python-lane-payloads.jsonl"
DEFAULT_SOURCE_ROOT = Path(os.environ.get(
    "FLYWHEEL_PYTHON_LANE_SOURCE_ROOT",
    str(ROOT / "build" / "python-lane-sources")))
SCHEMA = "flywheel.python-lane-source-stage/v1"
SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class StageError(RuntimeError):
    pass


def _load_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            lane = str(row["lane"])
            if lane in rows:
                raise StageError(f"duplicate lane row: {lane}")
            rows[lane] = row
    return rows


def _run(cmd: list[str], *, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise StageError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def _has_commit(repo: Path, commit: str) -> bool:
    proc = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False)
    return proc.returncode == 0


def _content_dirty(repo: Path) -> bool:
    subprocess.run(["git", "update-index", "--refresh"], cwd=repo,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    tracked = _run(["git", "diff", "--name-only"], cwd=repo)
    staged = _run(["git", "diff", "--cached", "--name-only"], cwd=repo)
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo)
    return bool(tracked or staged or untracked)


def _repo_source(row: dict[str, Any], overrides: dict[str, str]) -> str:
    lane = str(row["lane"])
    if lane in overrides:
        return overrides[lane]
    source_repo = str(row["component_descriptor"]["source"].get("repo", ""))
    if source_repo.startswith(("https://", "ssh://", "git@")) or (
            source_repo and (Path(source_repo) / ".git").exists()):
        return source_repo
    local = ROOT / str(row.get("registry_source_repo", ""))
    if (local / ".git").exists():
        return str(local)
    if str(row.get("registry_source_repo", "")).startswith("public/"):
        return "https://github.com/HarperZ9/" + Path(
            str(row["registry_source_repo"])).name + ".git"
    raise StageError(f"{lane}: no source repository available")


def _parse_repo_overrides(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        lane, sep, repo = value.partition("=")
        if not sep or not lane or not repo:
            raise StageError("--source-repo must be lane=repo")
        result[lane] = repo
    return result


def _require_safe_row(row: dict[str, Any]) -> None:
    lane, tag, commit = str(row["lane"]), str(row["owner_tag"]), str(row["owner_commit"])
    if not SAFE_TOKEN.fullmatch(lane) or not SAFE_TOKEN.fullmatch(tag):
        raise StageError(f"{lane}: unsafe lane/tag directory token")
    if not COMMIT.fullmatch(commit):
        raise StageError(f"{lane}: owner_commit must be a 40-hex SHA")


def _safe_dest(source_root: Path, row: dict[str, Any]) -> Path:
    root = source_root.resolve()
    dest = (source_root / f"{row['lane']}-{row['owner_tag']}").resolve()
    if dest != root and dest.is_relative_to(root):
        return dest
    raise StageError(f"{row['lane']}: destination escapes source root")


def _ensure_checkout(row: dict[str, Any], source_root: Path,
                     repo_source: str) -> Path:
    lane, tag = str(row["lane"]), str(row["owner_tag"])
    commit = str(row["owner_commit"])
    _require_safe_row(row)
    dest = _safe_dest(source_root, row)
    source_root.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not (dest / ".git").exists():
        raise StageError(f"{lane}: existing source path is not a git checkout: {dest}")
    if not dest.exists():
        _run(["git", "clone", "--no-checkout", "--filter=blob:none",
              "--no-tags", repo_source, str(dest)])
        _run(["git", "config", "core.autocrlf", "false"], cwd=dest)
        _run(["git", "config", "core.eol", "lf"], cwd=dest)
        if not _has_commit(dest, commit):
            _run(["git", "fetch", "origin", commit, "--depth", "1"], cwd=dest)
        _run(["git", "checkout", "--detach", commit], cwd=dest)
    elif _content_dirty(dest):
        raise StageError(f"{lane}: source checkout is dirty: {dest}")
    got = _run(["git", "rev-parse", "HEAD"], cwd=dest)
    # A pin may name a commit or an annotated tag object; peel it to the commit
    # it identifies so the check binds the exact tagged source, not the tag SHA.
    want = _run(["git", "rev-parse", f"{commit}^{{commit}}"], cwd=dest)
    if got != want:
        raise StageError(
            f"{lane}: existing stage is {got}, expected {want} (pin {commit}); "
            "use a fresh source root")
    return dest


def _hash_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _verify_manifest(row: dict[str, Any], checkout: Path) -> dict[str, Any]:
    files = row["component_descriptor"]["source"]["files"]
    total = 0
    root = checkout.resolve()
    for item in files:
        path = (checkout / item["path"]).resolve()
        if not path.is_relative_to(root):
            raise StageError(f"{row['lane']}: source file escapes checkout")
        if not path.is_file():
            raise StageError(f"{row['lane']}: missing {item['path']}")
        if _hash_file(path) != item["sha256"]:
            raise StageError(f"{row['lane']}: hash mismatch {item['path']}")
        size = path.stat().st_size
        if size != int(item["bytes"]):
            raise StageError(f"{row['lane']}: byte mismatch {item['path']}")
        total += size
    return {"file_count": len(files), "bytes": total}


def _bounded_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    lanes = []
    for row in receipt["lanes"]:
        lanes.append({
            "lane": row["lane"],
            "owner_commit": row["owner_commit"],
            "owner_tag": row["owner_tag"],
            "file_count": row["file_count"],
            "bytes": row["bytes"],
        })
    return {
        "schema": "flywheel.python-lane-source-stage-bounded/v1",
        "verdict": receipt["verdict"],
        "lanes": lanes,
        "omitted": ["source_root", "checkout_locations"],
    }


def stage_sources(args: argparse.Namespace) -> dict[str, Any]:
    rows = _load_rows(Path(args.manifest))
    overrides = _parse_repo_overrides(args.source_repo or [])
    staged = []
    lanes = sorted(rows) if getattr(args, "all", False) else (args.lane or ["canon"])
    for lane in lanes:
        if lane not in rows:
            raise StageError(f"unknown lane: {lane}")
        row = rows[lane]
        checkout = _ensure_checkout(
            row, Path(args.source_root), _repo_source(row, overrides))
        verified = _verify_manifest(row, checkout)
        staged.append({"lane": lane, "path": str(checkout.as_posix()),
                       "owner_commit": row["owner_commit"],
                       "owner_tag": row["owner_tag"], **verified})
    receipt = {"schema": SCHEMA, "verdict": "PASS",
               "source_root": str(Path(args.source_root).as_posix()),
               "lanes": staged}
    if args.receipt:
        Path(args.receipt).write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    if args.bounded_receipt:
        Path(args.bounded_receipt).write_text(
            json.dumps(_bounded_receipt(receipt), indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--lane", action="append")
    parser.add_argument("--all", action="store_true",
                        help="stage every manifest lane, not just --lane")
    parser.add_argument("--source-repo", action="append")
    parser.add_argument("--receipt")
    parser.add_argument("--bounded-receipt")
    args = parser.parse_args(argv)
    try:
        receipt = stage_sources(args)
    except (OSError, subprocess.SubprocessError, StageError, json.JSONDecodeError) as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"verdict": "PASS", "lanes": [row["lane"] for row in receipt["lanes"]]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
