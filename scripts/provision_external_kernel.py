"""Build the pinned external kernel (nanoda) and exporter (lean4export).

Usage:
    python scripts/provision_external_kernel.py --fetch
    python scripts/provision_external_kernel.py --archives DIR

--fetch downloads the two source archives named in
harness/lean_external_tools.PINS from their official GitHub repositories;
--archives reads the same files from DIR instead. Either way each archive's
sha256 must equal its pin before anything is extracted. nanoda builds with
`cargo build --release --locked` (its committed Cargo.lock pins every crate);
lean4export builds with `lake build` under the Lean toolchain that compiles
candidates, because an .olean loads only into the Lean build that wrote it.

The binaries land in <dir>/bin and the manifest in <dir>/manifest.json, where
<dir> is harness.lean_external_tools.tools_dir() unless --dir says otherwise.
The harness re-hashes both binaries against that manifest on every run.
Needs: cargo, elan (lake), network access with --fetch.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.lean_external_tools import (MANIFEST, PINS, SCHEMA,  # noqa: E402
                                         sha256_file, tools_dir)

EXE = ".exe" if sys.platform == "win32" else ""


def _say(msg: str) -> None:
    print(f"provision: {msg}", flush=True)


def _archive(key: str, work: Path, fetch: bool, source: "Path | None") -> Path:
    pin = PINS[key]
    name = f"{key}-{pin['commit'][:12]}.tar.gz"
    dest = work / name
    if fetch:
        _say(f"fetching {pin['archive_url']}")
        with urllib.request.urlopen(pin["archive_url"], timeout=120) as r, \
                open(dest, "wb") as fh:
            shutil.copyfileobj(r, fh)
    else:
        found = sorted((source or work).glob(f"*{pin['commit'][:7]}*.tar.gz"))
        found += sorted((source or work).glob(
            f"*{pin['version'].lstrip('v')}*.tar.gz"))
        if not found:
            raise SystemExit(f"no archive for {key} in {source}")
        shutil.copyfile(found[0], dest)
    got = sha256_file(dest)
    if got != pin["archive_sha256"]:
        dest.unlink()
        raise SystemExit(f"{key} archive sha256 {got} does not match the pin "
                         f"{pin['archive_sha256']}; refusing to build it")
    _say(f"{key} archive sha256 matches the pin")
    return dest


def _extract(archive: Path, work: Path) -> Path:
    out = work / archive.name.replace(".tar.gz", "")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with tarfile.open(archive) as tf:
        tf.extractall(out, filter="data")
    tops = [p for p in out.iterdir() if p.is_dir()]
    if len(tops) != 1:
        raise SystemExit(f"{archive.name} does not hold one top directory")
    return tops[0]


def _run(argv: list, cwd: Path) -> str:
    _say(" ".join(argv))
    r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{argv[0]} failed:\n{r.stdout[-2000:]}"
                         f"\n{r.stderr[-2000:]}")
    return r.stdout


def _lean_version() -> tuple:
    out = _run(["lean", "--version"], Path.cwd()).strip().splitlines()[0]
    version = out.split("version ", 1)[1].split(",", 1)[0].strip()
    githash = out.split("commit ", 1)[1].split(",", 1)[0].strip() \
        if "commit " in out else ""
    return version, githash


def _install(src: Path, bindir: Path, key: str, extra: dict) -> dict:
    bindir.mkdir(parents=True, exist_ok=True)
    dest = bindir / src.name
    shutil.copyfile(src, dest)
    entry = {k: PINS[key][k] for k in ("tool", "version", "commit",
                                       "archive_sha256", "archive_url",
                                       "repository", "license")}
    entry.update(binary=str(dest.resolve()),
                 binary_sha256=sha256_file(dest), **extra)
    return entry


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    how = ap.add_mutually_exclusive_group(required=True)
    how.add_argument("--fetch", action="store_true",
                     help="download the pinned archives from GitHub")
    how.add_argument("--archives", type=Path,
                     help="read the pinned archives from this directory")
    ap.add_argument("--dir", type=Path, default=None,
                    help="install directory (default: tools_dir())")
    args = ap.parse_args(argv)
    base = (args.dir or tools_dir()).resolve()
    work = base / "src"
    work.mkdir(parents=True, exist_ok=True)
    lean_version, githash = _lean_version()
    toolchain = f"leanprover/lean4:v{lean_version}"

    nanoda_src = _extract(_archive("nanoda", work, args.fetch, args.archives),
                          work)
    rustc = _run(["rustc", "--version"], nanoda_src).strip()
    _run(["cargo", "build", "--release", "--locked"], nanoda_src)
    nanoda = _install(nanoda_src / "target" / "release" / f"nanoda_bin{EXE}",
                      base / "bin", "nanoda", {"built_with": rustc})

    export_src = _extract(_archive("lean4export", work, args.fetch,
                                   args.archives), work)
    _run(["lake", f"+{toolchain}", "build"], export_src)
    export = _install(export_src / ".lake" / "build" / "bin" /
                      f"lean4export{EXE}", base / "bin", "lean4export",
                      {"lean_version": lean_version, "lean_githash": githash,
                       "built_with": toolchain})

    manifest = {"schema": SCHEMA,
                "tools": {"nanoda": nanoda, "lean4export": export}}
    (base / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n",
                                 encoding="utf-8")
    _say(f"wrote {base / MANIFEST}")
    for key, entry in manifest["tools"].items():
        _say(f"{key} {entry['version']} {entry['binary_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
