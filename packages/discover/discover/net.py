"""The few network reads discover makes, all optional and read-only.

GitHub repository metadata (description and topics) and the latest published
version on PyPI, npm or GitHub Releases. Each function returns None on any
network or parse failure; the caller reports that as a warning, so an offline
run never passes a check it could not perform.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 15
SLUG = re.compile(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$")


def _get(url: str, token: str | None = None) -> dict | None:
    headers = {"Accept": "application/json", "User-Agent": "discover-gate"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def repo_slug(root: str) -> str | None:
    """OWNER/REPO from GITHUB_REPOSITORY, else from the git remote."""
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    try:
        url = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    match = SLUG.search(url)
    return match.group(1) if match else None


def github_repo(slug: str) -> dict | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    return _get(f"https://api.github.com/repos/{slug}", token)


def latest_version(source: str, name: str) -> str | None:
    """Latest version of `name` on pypi, npm or github (OWNER/REPO, from the latest release tag)."""
    if source == "pypi":
        data = _get(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json")
        return data["info"]["version"] if data else None
    if source == "npm":
        data = _get(f"https://registry.npmjs.org/{name.replace('/', '%2F')}/latest")
        return data.get("version") if data else None
    if source == "github":
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        data = _get(f"https://api.github.com/repos/{name}/releases/latest", token)
        return data["tag_name"].lstrip("v") if data and data.get("tag_name") else None
    return None
