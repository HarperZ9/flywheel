"""switch.py -- put the brief where the next agent reads it on its own.

Switching to a target renders that target's workspace instruction file region:
the project's personality blocks (by the authored-split rule the rest of canon
uses) followed by one generated block holding the resume brief. The target
loads its instruction file at startup, so the brief reaches it without a paste.

The write goes through the same allow-list and region rules as every other
canon write: only a catalog surface, reached through no link, only between the
canon markers, and only into a file that already carries a region, or into a
file that does not exist yet when the caller asks for it to be created. The
host checks (links, the region, line endings, Codex's override file and byte
budget) are in `switch_host.py`. The brief is fitted to its budget as the block
that lands in the file, sentinel included, and the receipt carries the digest
of that block and of the whole region interior. IO is injected, so planning
reads and commit writes are separate steps.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from canon.layering import LayeringError
from canon.region import splice_region
from canon.registry import (
    SURFACE_CATALOG,
    Surface,
    assert_writable,
    pool_for,
    resolve_surface_path,
)
from canon.schema import KIND_PERSONALITY_BLOCK, Provenance, Record
from canon.surface import SurfaceError, render_surface
from canon.textblock import RenderRefused, recompute_source_hash, render_region
from canon.workspace import switch_host
from canon.workspace.brief import (
    Brief,
    make_brief,
    omitted_blocks,
    omitted_note,
    refuse_secrets,
)
from canon.workspace.hosts import cursor_frontmatter_problem, new_host_text
from canon.workspace.identity import ProjectIdentity
from canon.workspace.pool import TaggedRecord, block_pool
from canon.workspace.switch_host import SwitchRefused  # noqa: F401  (re-exported)
from canon.workspace.target_fidelity import brief_downgrades, downgrades_for
from canon.workspace.targets import Target

BRIEF_BLOCK_ID = "canon-workspace-brief"
BRIEF_HARNESS = "canon-handoff"


@dataclass(frozen=True, slots=True)
class SwitchPlan:
    target: Target
    brief: Brief
    surface: Surface | None
    path: str | None
    status: str
    old_text: str | None
    new_text: str | None
    interior: str | None
    warnings: tuple[str, ...]
    owners: dict = field(default_factory=dict)
    receipt: dict = field(default_factory=dict)


def workspace_surface(target: Target) -> Surface | None:
    for surface in SURFACE_CATALOG:
        if surface.harness == target.harness and surface.scope == "workspace":
            return surface
    return None


def block_owners(pool: list[TaggedRecord], surface: Surface) -> dict:
    """Which project (or `global`) owns each block the surface renders. A
    workspace block of this or a declared project wins over a global one with
    the same id, as layering resolves it."""
    owners: dict = {}
    for item in pool:
        rec = item.record
        if rec.kind != KIND_PERSONALITY_BLOCK:
            continue
        if rec.scope == "workspace":
            owners[rec.id] = item.project_id
        else:
            owners.setdefault(rec.id, "global")
    rendered = {b.id for b in pool_for(surface, block_pool(pool))}
    return {rid: owner for rid, owner in owners.items() if rid in rendered}


def brief_record(brief: Brief | str) -> Record:
    """The brief as a personality block: its heading becomes the block title and
    the rest its body, so the region grammar carries it unchanged."""
    text = brief if isinstance(brief, str) else brief.text
    lines = text.rstrip("\n").split("\n")
    title = lines[0].lstrip("#").strip()
    body = "\n".join(lines[2:])
    return Record(kind=KIND_PERSONALITY_BLOCK, id=BRIEF_BLOCK_ID, scope="workspace",
                  data={"title": title, "body": body},
                  provenance=Provenance(harness=BRIEF_HARNESS,
                                        source_hash=recompute_source_hash(title, body)))


def block_overhead() -> tuple[int, int]:
    """Bytes and lines the brief block adds to the brief text: its sentinel
    line, less the blank line under the heading that the block drops."""
    sample = "## T\n\nbody\n"
    rendered = render_region([brief_record(sample)], "workspace")
    return (len(rendered.encode("utf-8")) - len(sample.encode("utf-8")),
            rendered.count("\n") - sample.count("\n"))


def region_interior(pool: list[TaggedRecord], surface: Surface, brief: Brief) -> str:
    blocks = pool_for(surface, block_pool(pool))
    if any(b.id == BRIEF_BLOCK_ID for b in blocks):
        raise SwitchRefused("conflict", f"a stored block already uses the reserved id {BRIEF_BLOCK_ID!r}")
    try:
        return render_surface(blocks + [brief_record(brief)], "workspace")
    except (LayeringError, RenderRefused) as exc:
        raise SwitchRefused("conflict", f"the region cannot be rendered: {exc}") from exc


def _host(path: str, target: Target, read_text, create: bool) -> tuple[str, str]:
    host = read_text(path)
    if host is not None:
        return host, "write"
    if not create:
        raise SwitchRefused("not_found", f"{path} does not exist; pass --create to "
                                         "create it with a canon region")
    return new_host_text(target.name), "create"


def _host_warnings(target: Target, pool: list[TaggedRecord], surface: Surface,
                   text: str, brief: Brief) -> tuple[str, ...]:
    """What the target will do differently from what the blocks and the brief
    asked for, and a Cursor rule file Cursor would not load on every request."""
    warnings = []
    downs = downgrades_for(pool_for(surface, block_pool(pool)), target.name) + \
        brief_downgrades(brief.text, target.name)
    for down in downs:
        state = "declared" if down.declared else "UNDECLARED"
        warnings.append(f"block {down.record_id}: {down.feature} ({state}): {down.note}")
    if target.name == "cursor":
        problem = cursor_frontmatter_problem(text)
        if problem:
            warnings.append(problem)
    return tuple(warnings)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rendered(brief: Brief, interior: str) -> dict:
    block = render_region([brief_record(brief)], "workspace")
    return {**brief.receipt,
            "rendered_block": {"sha256": _sha(block), "bytes": len(block.encode("utf-8")),
                               "lines": block.count("\n")},
            "interior": {"sha256": _sha(interior), "bytes": len(interior.encode("utf-8"))}}


def _surface_path(surface: Surface, identity: ProjectIdentity, home: str) -> str:
    workspace = str(identity.root)
    path = resolve_surface_path(surface, home=home, workspace=workspace)
    try:
        assert_writable(path, home=home, workspace=workspace)
    except SurfaceError as exc:
        raise SwitchRefused("unsafe_path", str(exc)) from exc
    switch_host.safe_path(path, workspace)
    return path


def plan_switch(identity: ProjectIdentity, pool: list[TaggedRecord], target: Target, *,
                home: str, read_text, create: bool = False,
                budget_bytes: int | None = None, budget_lines: int | None = None,
                declared: tuple[str, ...] = (), check_limits: bool = True,
                receipt_hint: str | None = None,
                codex_home: str | None = None) -> SwitchPlan:
    """Read the target's surface and plan the rewrite. Writes nothing.
    `check_limits=False` skips the host size refusal, for a caller that only
    reads the region (pulling edits back) and will not write it. `codex_home`
    is the `CODEX_HOME` value, where Codex reads its config instead of
    `~/.codex`."""
    surface = workspace_surface(target)
    brief = make_brief(identity, pool, target, budget_bytes=budget_bytes,
                       budget_lines=budget_lines, declared=declared, level=2,
                       overhead=block_overhead() if surface else (0, 0),
                       receipt_hint=receipt_hint)
    if surface is None:
        note = omitted_note(omitted_blocks(brief))
        return SwitchPlan(target, brief, None, None, "no-surface", None, None, None,
                          (note,) if note else (), receipt=brief.receipt)
    path = _surface_path(surface, identity, home)
    if check_limits and surface.harness == "codex":
        switch_host.refuse_shadow(Path(identity.root))
    host, status = _host(path, target, read_text, create)
    region = switch_host.checked_region(host, path)
    interior = region_interior(pool, surface, brief)
    refuse_secrets(interior, "instruction region")
    eol = switch_host.host_newline(region)
    new_text = splice_region(host, interior.replace("\n", eol))
    if status == "write" and region.inner.replace("\r\n", "\n") == interior:
        status, new_text = "unchanged", host
    limits = switch_host.limits(target, new_text, root=Path(identity.root), home=home,
                                codex_home=codex_home) if check_limits else ()
    warnings = limits + _host_warnings(target, pool, surface, new_text, brief)
    old = None if status == "create" else host
    return SwitchPlan(target, brief, surface, path, status, old, new_text, interior, warnings,
                      block_owners(pool, surface), _rendered(brief, interior))


def commit_switch(plan: SwitchPlan, write_text, read_text=None) -> None:
    """Write the planned file when the plan changes it. With `read_text`, the
    file is read again first and the write is refused if it changed since the
    plan read it (or appeared, for a create), so an edit made in between is not
    overwritten. The window between that read and the write remains."""
    if plan.status not in ("write", "create"):
        return
    if read_text is not None and read_text(plan.path) != plan.old_text:
        raise SwitchRefused("conflict", f"{plan.path} changed while the switch was "
                                        "planned; nothing was written, run it again")
    write_text(plan.path, plan.new_text)
