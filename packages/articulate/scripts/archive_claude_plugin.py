#!/usr/bin/env python3
"""Validate a built plugin and write deterministic ZIP/MCPB archives and checksums.

    python scripts/archive_claude_plugin.py PLUGIN_DIR OUT_DIR

This packages a bundle; the build command owns release-tag checks. Use a release
build for publication. ZIP_STORED avoids compressor-version-dependent bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claude_plugin_rules as rules  # noqa: E402


def _contained_files(root):
    return [path for path in rules.contained_entries(root) if path.is_file()]


def mcpb_manifest(plugin):
    """Generate MCPB 0.3 metadata from the checked bundle, without a new runtime."""
    identity = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
    launch = json.loads((plugin / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["articulate"]
    return {
        "manifest_version": "0.3",
        "name": identity["name"], "version": identity["version"],
        "display_name": "Articulate Writing",
        "description": identity["description"],
        "long_description": "Local prose checks and guarded host edits. Requires an already-installed "
                            "Python 3.9 or later executable. This extension includes server source, "
                            "not a Python interpreter. Select your Python executable during setup.",
        "author": identity["author"], "homepage": identity["homepage"],
        "license": identity["license"], "keywords": identity["keywords"],
        "repository": {"type": "git", "url": identity["repository"]},
        "server": {
            "type": "python", "entry_point": "server/serve.py",
            "mcp_config": {
                "command": "${user_config.python_path}",
                "args": launch["args"][:-1] + ["${__dirname}/server/serve.py"],
                "env": launch["env"],
            },
        },
        "compatibility": {"platforms": ["darwin", "win32"], "runtimes": {"python": ">=3.9"}},
        "user_config": {"python_path": {
            "type": "file", "title": "Python 3.9+ executable", "required": True,
            "description": "Select an installed Python executable (python.exe on Windows, "
                           "python3 on macOS). Python is not included in this extension.",
        }},
    }


def _checksums(out, targets):
    with (out / "SHA256SUMS").open("w", encoding="utf-8", newline="\n") as checksum:
        for target in sorted(targets):
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            checksum.write(f"{digest}  {target.name}\n")


def archive(plugin_dir, out_dir, format="plugin"):
    if format not in ("plugin", "mcpb"):
        raise ValueError("unknown archive format")
    plugin, out = Path(plugin_dir).absolute(), Path(out_dir).resolve()
    boundary = plugin.resolve()
    if out == boundary or boundary in out.parents:
        raise ValueError("archive destination must be outside the plugin folder")
    safe_files = _contained_files(plugin)
    problems = rules.check_bundle(plugin)
    if problems:
        raise ValueError("invalid plugin bundle: " + "; ".join(problems))
    version = rules.bundled_version(plugin)
    if not version or not re.fullmatch(r"[0-9A-Za-z.+-]+", version):
        raise ValueError("invalid archive version")
    # Snapshot bytes after validation; paths in the ZIP have no outer wrapper.
    if format == "mcpb":
        safe_files = [p for p in safe_files
                      if p.relative_to(plugin).parts[0] in ("src", "server")
                      or p.relative_to(plugin).as_posix() in ("LICENSE", "README.md", "PRIVACY.md", "SECURITY.md")]
    files = [(p.relative_to(plugin).as_posix(), p.read_bytes()) for p in safe_files]
    if format == "mcpb":
        manifest = (json.dumps(mcpb_manifest(plugin), indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        files.append(("manifest.json", manifest))
    out.mkdir(parents=True, exist_ok=True)
    suffix = "plugin.zip" if format == "plugin" else "desktop.mcpb"
    target = out / f"articulate-writing-{version}-{suffix}"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as bundle:
        for name, data in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100644 << 16)
            bundle.writestr(info, data)
    _checksums(out, [target])
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plugin_dir")
    parser.add_argument("out_dir")
    parser.add_argument("--format", choices=("plugin", "mcpb", "both"), default="plugin")
    args = parser.parse_args(argv)
    formats = ("plugin", "mcpb") if args.format == "both" else (args.format,)
    targets = [archive(args.plugin_dir, args.out_dir, format=fmt) for fmt in formats]
    _checksums(Path(args.out_dir), targets)
    for target in targets:
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
