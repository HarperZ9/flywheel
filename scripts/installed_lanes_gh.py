"""Read one installed-app acceptance run from GitHub, read-only, and check its artifact.

make_installed_lanes_evidence.py --from-gh uses this. It checks the workflow path,
repository, branch and source SHA against GitHub and the artifact's workflow_source.
The run must be completed with success and have one successful job. It reads the
run's artifact and that artifact's sha256 digest, downloads the artifact zip,
and checks the zip against the digest. When the local artifact folder already
holds the artifact, every file in it must equal its zip member byte for byte,
with no file missing and none extra; when it holds none, the zip is extracted
there. Every gh call here is a GET.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ARTIFACT_PREFIX = "windows-installed-acceptance-"
WORKFLOW_PATH = ".github/workflows/windows-installed-acceptance.yml"


def _gh(args: list[str], runner=subprocess.run) -> bytes:
    done = runner(["gh", *args], capture_output=True, check=False)
    if done.returncode != 0:
        err = done.stderr.decode("utf-8", "replace").strip()
        raise SystemExit(f"gh {' '.join(args[:3])} failed: {err}")
    return done.stdout


def run_meta(repo: str, run_id: int, runner=subprocess.run) -> dict:
    """Job id, start date and artifact id and digest of a finished, successful run."""
    view = json.loads(_gh(["run", "view", str(run_id), "-R", repo, "--json",
                           "status,conclusion,headSha,jobs"], runner))
    if (view.get("status"), view.get("conclusion")) != ("completed", "success"):
        raise SystemExit(f"run {run_id} is {view.get('status')}/{view.get('conclusion')}")
    source = json.loads(_gh(["api", f"repos/{repo}/actions/runs/{run_id}"], runner))
    if source.get("path") != WORKFLOW_PATH:
        raise SystemExit(f"run {run_id}: workflow path is not {WORKFLOW_PATH}")
    repository = source.get("repository")
    branch, sha = source.get("head_branch"), source.get("head_sha")
    if (not isinstance(repository, dict) or repository.get("full_name") != repo
            or not isinstance(branch, str) or not branch
            or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or sha != view.get("headSha")):
        raise SystemExit(f"run {run_id}: workflow source repository, branch or SHA mismatch")
    jobs = view.get("jobs") or []
    if len(jobs) != 1 or jobs[0].get("conclusion") != "success":
        raise SystemExit(f"run {run_id}: expected one successful job, found {jobs}")
    listing = json.loads(_gh(["api", f"repos/{repo}/actions/runs/{run_id}/artifacts"], runner))
    name = f"{ARTIFACT_PREFIX}{run_id}"
    found = [a for a in listing.get("artifacts", []) if a.get("name") == name]
    if len(found) != 1 or found[0].get("expired"):
        raise SystemExit(f"run {run_id}: no unexpired artifact named {name}")
    digest = str(found[0].get("digest") or "")
    if not digest.startswith("sha256:"):
        raise SystemExit(f"run {run_id}: artifact {name} has no sha256 digest")
    return {"run_id": run_id, "job_id": jobs[0]["databaseId"],
            "date": jobs[0]["startedAt"][:10], "head_sha": view.get("headSha"),
            "workflow_source": {"repository": repo, "ref": f"refs/heads/{branch}", "sha": sha},
            "artifact_id": found[0]["id"], "artifact_name": name,
            "artifact_zip_sha256": digest.split(":", 1)[1]}


def _members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        out = {}
        for info in zf.infolist():
            if info.is_dir():
                continue
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or ":" in info.filename:
                raise SystemExit(f"artifact zip member {info.filename!r} leaves the folder")
            out[path.as_posix()] = zf.read(info)
    return out


def match_or_extract(data: bytes, sha256: str, folder: Path, name: str) -> Path:
    """Check the zip against its digest, then against the folder or into it."""
    if hashlib.sha256(data).hexdigest() != sha256:
        raise SystemExit("the downloaded artifact zip does not match its digest")
    members = _members(data)
    summary = "ci-installed-acceptance-summary.json"
    if (folder / summary).is_file():
        target = folder
    elif (folder / name / summary).is_file():
        target = folder / name
    else:
        target = folder / name
        for rel, body in members.items():
            (target / rel).parent.mkdir(parents=True, exist_ok=True)
            (target / rel).write_bytes(body)
        return target
    local = {p.relative_to(target).as_posix(): p for p in target.rglob("*") if p.is_file()}
    if set(local) != set(members):
        raise SystemExit(f"{target}: files differ from the artifact zip: "
                         f"{sorted(set(local) ^ set(members))}")
    changed = sorted(rel for rel, p in local.items() if p.read_bytes() != members[rel])
    if changed:
        raise SystemExit(f"{target}: files differ from their zip members: {changed}")
    return target


def fetch_and_verify(repo: str, run_id: int, folder: Path, runner=subprocess.run,
                     *, expected_commit: str) -> dict:
    meta = run_meta(repo, run_id, runner)
    if meta["head_sha"] != expected_commit:
        raise SystemExit(f"run {run_id}: workflow head SHA is not {expected_commit}")
    data = _gh(["api", f"repos/{repo}/actions/artifacts/{meta['artifact_id']}/zip"], runner)
    folder.mkdir(parents=True, exist_ok=True)
    target = match_or_extract(data, meta["artifact_zip_sha256"], folder, meta["artifact_name"])
    summary = json.loads((target / "ci-installed-acceptance-summary.json").read_text("utf-8-sig"))
    if summary.get("workflow_source") != meta["workflow_source"]:
        raise SystemExit(f"run {run_id}: artifact workflow_source differs from GitHub metadata")
    print(f"run {run_id}: job {meta['job_id']}, {meta['date']}, head {meta['head_sha']}, "
          f"artifact zip sha256 {meta['artifact_zip_sha256']} matches")
    return {k: meta[k] for k in ("run_id", "job_id", "date", "artifact_zip_sha256")}
