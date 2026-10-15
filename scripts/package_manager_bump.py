"""Point the Homebrew formula and the Scoop manifest at one PyPI release.

    python scripts/package_manager_bump.py            # the pyproject.toml version
    python scripts/package_manager_bump.py 1.9.0      # a named version
    python scripts/package_manager_bump.py --check    # compare, change nothing

Formula/flywheel.rb installs the release's sdist and bucket/flywheel.json
installs its wheel. Both pin a SHA-256 that exists only once PyPI has the
release, so the release PR cannot carry it. After publish.yml has put the
release on PyPI, run this script and commit the two files in a follow-up PR.
The files trail pyproject.toml by one release only in that window, and
tests/test_package_manager_manifests.py allows nothing wider.

The digests come from PyPI's JSON API over HTTPS. Standard library only.
"""
from __future__ import annotations

import json
import re
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORMULA = ROOT / "Formula" / "flywheel.rb"
MANIFEST = ROOT / "bucket" / "flywheel.json"
PROJECT = "flywheel-verify"
WHEEL_URL = ("https://files.pythonhosted.org/packages/py3/f/flywheel-verify/"
             "flywheel_verify-{version}-py3-none-any.whl")


def pyproject_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def pypi_release(version: str, attempts: int = 5) -> dict[str, str]:
    """The sdist URL and digest and the wheel digest PyPI lists for `version`."""
    url = f"https://pypi.org/pypi/{PROJECT}/{version}/json"
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                files = json.load(resp)["urls"]
            break
        except OSError as exc:  # a release seconds old can 404 until PyPI's CDN catches up
            print(f"PyPI {url}: {exc} (attempt {attempt + 1} of {attempts})", file=sys.stderr)
            if attempt + 1 == attempts:
                raise
            time.sleep(15)
    by_type = {f["packagetype"]: f for f in files}
    missing = {"sdist", "bdist_wheel"} - by_type.keys()
    if missing:
        raise SystemExit(f"PyPI lists no {sorted(missing)} for {PROJECT} {version}")
    return {"sdist_url": by_type["sdist"]["url"],
            "sdist_sha256": by_type["sdist"]["digests"]["sha256"],
            "wheel_sha256": by_type["bdist_wheel"]["digests"]["sha256"]}


def pypi_has(version: str) -> bool:
    """True when PyPI lists `version` of the project, False on a 404."""
    try:
        pypi_release(version, attempts=1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise
    return True


def render_formula(text: str, release: dict[str, str]) -> str:
    text, n_url = re.subn(r'^(  url ")[^"]+(")$',
                          lambda m: m.group(1) + release["sdist_url"] + m.group(2), text, flags=re.M)
    text, n_sha = re.subn(r'^(  sha256 ")[0-9a-f]{64}(")$',
                          lambda m: m.group(1) + release["sdist_sha256"] + m.group(2), text, flags=re.M)
    if (n_url, n_sha) != (1, 1):
        raise SystemExit(f"{FORMULA.name}: expected one url and one sha256 line, found {n_url} and {n_sha}")
    return text


def render_manifest(text: str, version: str, release: dict[str, str]) -> str:
    manifest = json.loads(text)
    manifest["version"] = version
    manifest["url"] = WHEEL_URL.format(version=version)
    manifest["hash"] = release["wheel_sha256"]
    return json.dumps(manifest, indent=4) + "\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    version = args[0] if args else pyproject_version()
    release = pypi_release(version)
    wanted = {FORMULA: render_formula(FORMULA.read_text(encoding="utf-8"), release),
              MANIFEST: render_manifest(MANIFEST.read_text(encoding="utf-8"), version, release)}
    stale = [p for p, text in wanted.items() if p.read_text(encoding="utf-8") != text]
    for path in stale:
        rel = path.relative_to(ROOT).as_posix()
        if check:
            print(f"{rel} does not match PyPI {PROJECT} {version}", file=sys.stderr)
        else:
            path.write_text(wanted[path], encoding="utf-8", newline="\n")
            print(f"{rel} now points at {PROJECT} {version}")
    if not stale:
        print(f"Formula and Scoop manifest match PyPI {PROJECT} {version}")
    return 1 if check and stale else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
