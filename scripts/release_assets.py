"""release_assets.py -- what publish.yml runs to build and check a release.

One version tag ships the release. This script holds the parts of that which
are plain Python, so a person can run each one from a checkout:

    python scripts/release_assets.py check [--tag vX.Y.Z] [--release]
    python scripts/release_assets.py build --dist dist --out release-assets [--dev]
    python scripts/release_assets.py verify release-assets
    python scripts/release_assets.py pypi --version X.Y.Z --sums release-assets/python-SHA256SUMS.txt
    python scripts/release_assets.py gate-tests [--run]

- check: the tag, pyproject.toml, desktop/pubspec.yaml,
  desktop/lib/version.dart and CITATION.cff name one version, and the notes
  file for it exists,
  has the right heading and links the licensing page. With --release it also
  refuses a placeholder left in the notes, the changelog or SECURITY.md.
- build: copies the wheel and sdist from --dist and builds the plugin and
  skill zips, the source tools plugin and the VS Code extension. Each built
  file is built twice and the two results must be the same bytes. Every file
  is listed in one sums file. --dev builds the source plugin from a commit
  that is not the version tag (a dry run).
- verify: every sums line matches its file, and every file is in one sums
  file. One changed byte, a missing file or an unlisted file fails.
- pypi: PyPI lists the version and serves files with the digests the build
  wrote. It asks again while the release is not listed yet.
- gate-tests: prints the test files that carry the `release_gate` marker;
  --run runs them. publish.yml runs them against the installed wheel.

Standard library only. The Windows installer and the native MCPB companion
are built by desktop-release.yml and are not handled here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = "release_gate"
PLACEHOLDERS = ("SECURITY-WINDOW-END", "RELEASE-DATE")
SUMS_SUFFIX = "SHA256SUMS.txt"
PYPI = "https://pypi.org/pypi/flywheel-verify"


def declared_version(root: Path = ROOT) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"(.+?)"', text, re.M).group(1)


def version_sites(root: Path = ROOT) -> dict[str, str]:
    pub = re.search(r"^version:\s*(.+)$",
                    (root / "desktop" / "pubspec.yaml").read_text(encoding="utf-8"), re.M)
    dart = re.search(r"appVersion\s*=\s*['\"](.+?)['\"]",
                     (root / "desktop" / "lib" / "version.dart").read_text(encoding="utf-8"))
    cff = re.search(r'^version:\s*"?([^"\s]+)"?\s*$',
                    (root / "CITATION.cff").read_text(encoding="utf-8"), re.M)
    return {"pyproject.toml": declared_version(root),
            "desktop/pubspec.yaml": pub.group(1).split("+")[0].strip() if pub else "",
            "desktop/lib/version.dart": dart.group(1) if dart else "",
            "CITATION.cff": cff.group(1) if cff else ""}


def check(root: Path = ROOT, tag: str = "", release: bool = False) -> list[str]:
    """Every reason this tree must not be released as `tag`. Empty means none."""
    sites = version_sites(root)
    version = sites["pyproject.toml"]
    problems = [f"{name} declares {found}, pyproject.toml declares {version}"
                for name, found in sites.items() if found != version]
    if tag and tag != f"v{version}":
        problems.append(f"tag {tag} does not match the declared version {version}")
    notes = root / f"RELEASE-NOTES-{version}.md"
    if not notes.exists():
        return problems + [f"{notes.name} does not exist"]
    text = notes.read_text(encoding="utf-8")
    heading = next((ln for ln in text.splitlines() if ln.startswith("# ")), "")
    if heading != f"# Flywheel {version}":
        problems.append(f"{notes.name} opens with {heading!r}, not '# Flywheel {version}'")
    if "docs/LICENSING.md" not in text:
        problems.append(f"{notes.name} does not link docs/LICENSING.md")
    major = version.split(".")[0]
    migrating = f"docs/MIGRATING-{major}.0.md"
    if version.endswith(".0.0") and (root / migrating).exists() and migrating not in text:
        problems.append(f"{notes.name} does not link {migrating}")
    if release:
        problems += _unfilled(root, notes, version)
    return problems


def _unfilled(root: Path, notes: Path, version: str) -> list[str]:
    out = []
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"^## {re.escape(version)} \(\d{{4}}-\d{{2}}-\d{{2}}\)$", changelog, re.M):
        out.append(f"CHANGELOG.md has no dated '## {version} (YYYY-MM-DD)' section")
    for path in (notes, root / "CHANGELOG.md", root / "SECURITY.md"):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        out += [f"{path.name} still holds the placeholder {word}"
                for word in PLACEHOLDERS if word in text]
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*args: str) -> None:
    done = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"{' '.join(args)} failed:\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}")


def _build_once(folder: Path, dev: bool) -> dict[str, list[Path]]:
    """One build of the three pure-Python asset groups, each in its own folder."""
    plugins, source, vscode = folder / "plugins", folder / "source", folder / "vscode"
    _run("scripts/build_skill_bundle.py", "--out", str(plugins))
    _run("scripts/build_source_tool_plugin.py", "--out", str(source), *(["--dev"] if dev else []))
    package = json.loads((ROOT / "integrations" / "vscode" / "package.json")
                         .read_text(encoding="utf-8"))
    _run("scripts/build_vscode_vsix.py", "--out",
         str(vscode / f"flywheel-code-{package['version']}.vsix"))
    return {"plugin": sorted(plugins.glob("*.zip")), "source-plugin": sorted(source.glob("*.zip")),
            "vscode": sorted(vscode.glob("*.vsix"))}


def write_sums(out: Path, group: str, files: list[Path]) -> Path:
    """`<group>-SHA256SUMS.txt` in the form `sha256sum -c` reads, LF line ends."""
    lines = "".join(f"{sha256(path)}  {path.name}\n" for path in sorted(files))
    target = out / f"{group}-{SUMS_SUFFIX}"
    target.write_bytes(lines.encode("ascii"))
    return target


def build(dist: Path, out: Path, dev: bool = False) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise SystemExit(f"{out} is not empty; an asset is never written over another")
    python = sorted([*dist.glob("*.whl"), *dist.glob("*.tar.gz")])
    if len(python) != 2:
        raise SystemExit(f"{dist} must hold one wheel and one sdist, found {len(python)} files")
    with tempfile.TemporaryDirectory() as tmp:
        first, second = _build_once(Path(tmp) / "a", dev), _build_once(Path(tmp) / "b", dev)
        for group, files in first.items():
            again = {path.name: sha256(path) for path in second[group]}
            if {path.name: sha256(path) for path in files} != again or not files:
                raise SystemExit(f"{group}: two builds of the same commit gave different files")
        groups = {"python": python, **first}
        for group, files in groups.items():
            copies = [Path(shutil.copy2(path, out / path.name)) for path in files]
            write_sums(out, group, copies)
    verify(out)
    return sorted(out.iterdir())


def verify(folder: Path) -> dict[str, str]:
    """{file name: sha256} for a folder whose sums files all hold. Raises SystemExit."""
    listed: dict[str, str] = {}
    sums = sorted(folder.glob(f"*{SUMS_SUFFIX}"))
    if not sums:
        raise SystemExit(f"{folder} holds no sums file")
    for path in sums:
        for line in path.read_text(encoding="ascii").splitlines():
            digest, _, name = line.partition("  ")
            if not re.fullmatch(r"[0-9a-f]{64}", digest) or not name or name in listed:
                raise SystemExit(f"{path.name}: bad or repeated line {line!r}")
            target = folder / name
            if not target.is_file():
                raise SystemExit(f"{path.name} lists {name}, which is missing")
            if sha256(target) != digest:
                raise SystemExit(f"{name} does not match {path.name}")
            listed[name] = digest
    unlisted = [p.name for p in folder.iterdir() if p not in sums and p.name not in listed]
    if unlisted:
        raise SystemExit(f"in no sums file: {', '.join(sorted(unlisted))}")
    return listed


def read_sums(path: Path) -> dict[str, str]:
    return {name: digest for digest, _, name in
            (line.partition("  ") for line in path.read_text(encoding="ascii").splitlines())}


def _pypi_json(version: str) -> dict:
    with urllib.request.urlopen(f"{PYPI}/{version}/json", timeout=30) as reply:
        return json.load(reply)


def pypi(version: str, sums: Path, fetch=_pypi_json, tries: int = 20, wait: float = 15.0) -> list[str]:
    """Reasons PyPI's files for `version` are not the built ones. Empty means none.

    PyPI can take a moment to list a new release, so a missing release is asked
    for again. A digest that differs is final and is never asked for twice.
    """
    built = read_sums(sums)
    for attempt in range(tries):
        try:
            served = {f["filename"]: f["digests"]["sha256"] for f in fetch(version)["urls"]}
        except (OSError, KeyError, ValueError) as err:
            served, reason = {}, f"PyPI does not list {version} yet ({type(err).__name__})"
        else:
            reason = f"PyPI lists {sorted(served)} for {version}, the build made {sorted(built)}"
        if set(served) == set(built):
            return [f"{name}: PyPI serves {served[name]}, the build made {digest}"
                    for name, digest in sorted(built.items()) if served[name] != digest]
        if attempt + 1 < tries:
            time.sleep(wait)
    return [reason]


def gate_tests(root: Path = ROOT) -> list[str]:
    """Test files that carry the release_gate marker, as posix paths from the root."""
    return sorted(path.relative_to(root).as_posix() for path in (root / "tests").glob("test_*.py")
                  if f"mark.{MARKER}" in path.read_text(encoding="utf-8", errors="replace"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("check")
    one.add_argument("--tag", default="")
    one.add_argument("--release", action="store_true")
    two = sub.add_parser("build")
    two.add_argument("--dist", required=True)
    two.add_argument("--out", required=True)
    two.add_argument("--dev", action="store_true")
    sub.add_parser("verify").add_argument("folder")
    sub.add_parser("gate-tests").add_argument(
        "--run", action="store_true", help="run them with pytest -m release_gate")
    live = sub.add_parser("pypi")
    live.add_argument("--version", required=True)
    live.add_argument("--sums", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "pypi":
        problems = pypi(args.version, Path(args.sums))
        print("\n".join(problems) if problems
              else f"PyPI serves the built files for {args.version}")
        return 1 if problems else 0
    if args.cmd == "check":
        problems = check(tag=args.tag, release=args.release)
        print("\n".join(problems) if problems
              else f"release check clean for {declared_version()}")
        return 1 if problems else 0
    if args.cmd == "build":
        for path in build(Path(args.dist), Path(args.out), args.dev):
            print(f"{sha256(path)}  {path.name}")
        return 0
    if args.cmd == "verify":
        for name, digest in sorted(verify(Path(args.folder)).items()):
            print(f"{digest}  {name}")
        return 0
    files = gate_tests()
    print("\n".join(files) if files else f"no test file carries the {MARKER} marker")
    if not files or not args.run:
        return 0 if files else 1
    return subprocess.run([sys.executable, "-m", "pytest", "-m", MARKER, *files, "-q",
                           "-p", "no:cacheprovider"], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
