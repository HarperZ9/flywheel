"""switch_host.py -- what a switch checks about the host file before writing it.

- The path. The allow-list check is lexical, so the file and every directory
  above it inside the workspace are also checked for a symlink, junction or
  other reparse point, which would carry the write outside the repository or
  onto another surface. `canon.path_policy` does the check.
- The region. A file is written only when it carries exactly one canon region
  of workspace scope; the refusal for a file with none prints the two marker
  lines to add.
- The line endings. A host whose begin marker ends in CRLF gets a CRLF
  interior, so a file stays one line-ending style and an EOL-only difference
  is not a change.
- Codex. Codex reads AGENTS.override.md instead of AGENTS.md when both sit in a
  directory, so a switch that would write a file Codex never reads is refused.
  Codex also applies one byte budget (`project_doc_max_bytes`, 32768 unless
  its config.toml sets another) to every AGENTS file from the project root
  down to the working directory, so the root file is refused past the budget
  and a nested file the combined chain would cut is named in a warning. The
  config is read where Codex reads it: under `CODEX_HOME` when that is set,
  else under `~/.codex`.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

from canon.path_policy import PathPolicyError, resolve_under_root
from canon.region import RegionError, extract_region
from canon.workspace.targets import Target

REGION_LINES = "<!-- canon:begin scope=workspace -->\n<!-- canon:end -->"
_CODEX_FILES = ("AGENTS.override.md", "AGENTS.md")
_PRUNE = {".git", "node_modules"}
_WALK_LIMIT = 5000


class SwitchRefused(Exception):
    """The switch cannot write this target; `code` is the CLI failure code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def safe_path(path: str, workspace: str) -> None:
    """Refuse a surface path that runs through a link or reparse point."""
    try:
        resolve_under_root(path, root=workspace, reject_reparse=True)
    except PathPolicyError as exc:
        raise SwitchRefused("unsafe_path", f"{path}: {exc}") from exc


def checked_region(host: str, path: str):
    try:
        region = extract_region(host)
    except RegionError as exc:
        raise SwitchRefused("conflict", f"{path}: deformed canon region: {exc}") from exc
    if not region.present:
        raise SwitchRefused("conflict", f"{path} has no canon region. To let canon write "
                                        f"it, add these two lines where canon may write: "
                                        f"{REGION_LINES}")
    if region.scope != "workspace":
        raise SwitchRefused("conflict", f"{path}: region scope is {region.scope!r}, "
                                        "not workspace")
    return region


def host_newline(region) -> str:
    return "\r\n" if region.prefix.endswith("\r\n") else "\n"


def codex_config(home: str, codex_home: str | None) -> tuple[Path, str]:
    """The config file Codex reads and how to name its place: under
    `CODEX_HOME` when that is set, else under `~/.codex` in `home`."""
    if codex_home:
        return Path(codex_home) / "config.toml", "CODEX_HOME"
    return Path(home) / ".codex" / "config.toml", "~/.codex"


def codex_budget(home: str, default: int, codex_home: str | None = None) -> tuple[int, str]:
    """project_doc_max_bytes from the Codex config, else the documented
    default, and where the number came from. A config canon cannot parse
    leaves the default."""
    path, place = codex_config(home, codex_home)
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8")).get("project_doc_max_bytes")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return default, f"the Codex default; no value in config.toml under {place}"
    if isinstance(value, int) and value > 0:
        return value, f"from config.toml under {place}"
    return default, f"the Codex default; no value in config.toml under {place}"


def refuse_shadow(root: Path) -> None:
    if (root / "AGENTS.override.md").exists():
        raise SwitchRefused(
            "shadowed", "AGENTS.override.md sits next to AGENTS.md, and Codex reads the "
            "override instead, so it would never see what canon writes. Remove or rename "
            "the override, or move its text into AGENTS.md outside the canon region")


def _agents_files(root: Path) -> dict[tuple[str, ...], tuple[str, int]]:
    """Directory parts to (file name, bytes) for each directory under the root
    holding a file Codex would read, the override first."""
    found: dict = {}
    for count, (current, dirs, files) in enumerate(os.walk(root)):
        dirs[:] = sorted(d for d in dirs if d not in _PRUNE and not d.startswith("."))
        if count >= _WALK_LIMIT:
            break
        name = next((f for f in _CODEX_FILES if f in files), None)
        parts = Path(current).relative_to(root).parts
        if name and parts:
            found[parts] = (name, os.path.getsize(os.path.join(current, name)))
    return found


def nested_codex_warnings(root: Path, root_bytes: int, budget: int) -> list[str]:
    """A warning for each nested AGENTS file Codex would cut, because the files
    from the project root down to it share one budget."""
    files = _agents_files(root)
    warnings = []
    for parts in sorted(files):
        total, cut = root_bytes, None
        for depth in range(1, len(parts) + 1):
            entry = files.get(parts[:depth])
            if entry is None:
                continue
            total += entry[1]
            if cut is None and total > budget:
                cut = "/".join(parts[:depth] + (entry[0],))
        if cut is not None and parts in files:
            warnings.append(f"Codex run from {'/'.join(parts)} reads {total} bytes of AGENTS "
                            f"files, over its {budget}-byte budget; it truncates {cut}")
    return warnings


def limits(target: Target, text: str, *, root: Path, home: str,
           codex_home: str | None = None) -> tuple[str, ...]:
    size = len(text.encode("utf-8"))
    budget, raise_it = target.file_bytes_limit, ""
    if target.name == "codex" and budget is not None:
        budget, source = codex_budget(home, budget, codex_home)
        raise_it = (f" (project_doc_max_bytes, {source}); raise project_doc_max_bytes "
                    "in config.toml under CODEX_HOME, or ~/.codex when CODEX_HOME is "
                    "unset, or shorten the file")
    if budget is not None and size > budget:
        raise SwitchRefused(
            "budget_too_small", f"the file would be {size} bytes; {target.display} "
            f"reads at most {budget} and truncates the rest{raise_it}")
    warnings = nested_codex_warnings(root, size, budget) if target.name == "codex" else []
    lines = text.count("\n")
    if target.file_lines_advice is not None and lines > target.file_lines_advice:
        warnings.append(f"the file is {lines} lines; {target.display} guidance is under "
                        f"{target.file_lines_advice}")
    return tuple(warnings)
