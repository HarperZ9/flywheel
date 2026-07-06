"""boot.py — the invocation-time hydration packet (Layer-1 auto-injection).

Composes a minimum-token snapshot of endpoint state — system, workspace, goals,
decisions — emitted at launch so any model (frozen enterprise included) boots
into the operator's situation without cold-starting and without knowing it has
tools. Minimum-token via lossless-by-ref: the model gets shape + digests +
expansion commands, not raw bytes.

Freshness-gated: verify_boot() re-walks the tree and recomputes root_hash; any
drift collapses the packet to UNVERIFIABLE before the model acts on it. A stale
boot packet degrades every model equally, so the gate is load-bearing, not
optional machinery. Aligned to the project-telos.context-envelope/v1 contract
shape so it composes with the index/forum/crucible organs later.
"""
from __future__ import annotations
import hashlib
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules",
             ".ruff_cache", "workdir", "envelopes", ".venv", "venv"}
SOURCE_EXT = {".py", ".md", ".sh", ".cmd", ".json", ".toml", ".cfg"}


@dataclass
class SourceRef:
    id: str
    path: str
    content_hash: str
    bytes: int
    lines: int
    expansion: str


@dataclass
class BootPacket:
    envelope_id: str
    workspace_root: str
    root_hash: str
    git_head: str | None
    context_budget: int
    packet_tokens_approx: int
    system: dict
    source_refs: list[SourceRef] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    receipt_chain: list[dict] = field(default_factory=list)
    failure_code: str | None = None
    verdict: str = "MATCH"

    def to_dict(self) -> dict:
        return asdict(self)

    def root_receipt(self) -> dict:
        return {"stage": "boot", "root_hash": self.root_hash,
                "git_head": self.git_head, "verdict": self.verdict,
                "failure_code": self.failure_code}


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _manifest(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in SOURCE_EXT:
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def _root_hash(files: list[Path], root: Path) -> str:
    h = hashlib.sha256()
    for p in files:
        rel = p.relative_to(root).as_posix()
        h.update(rel.encode())
        h.update(_sha_file(p).encode())
    return h.hexdigest()[:16]


def _git_head(root: Path) -> str | None:
    try:
        r = subprocess.run(
            "git rev-parse HEAD", cwd=str(root), shell=True,
            capture_output=True, timeout=5, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if r.returncode == 0:
            return r.stdout.decode().strip()[:16]
    except Exception:
        pass
    return None


def _system_slot(root: Path) -> dict:
    harness_dir = root / "harness"
    modules = sorted(p.stem for p in harness_dir.glob("*.py")) if harness_dir.is_dir() else []
    proposers = ["stub", "serve", "enterprise"]
    oracles = ["pytest", "stub"]
    return {
        "python": platform.python_version(),
        "platform": sys.platform,
        "harness_modules": modules,
        "proposers_available": proposers,
        "oracles_available": oracles,
    }


def _goals_slot(root: Path) -> dict:
    state = root / "STATE.md"
    phase, updated = "unknown", "unknown"
    if state.is_file():
        txt = state.read_text(encoding="utf-8", errors="replace")
        m_phase = re.search(r"^##\s*Phase.*$", txt, re.M)
        m_upd = re.search(r"^Last updated:\s*(.+)$", txt, re.M)
        if m_phase:
            phase = m_phase.group(0).strip()
        if m_upd:
            updated = m_upd.group(1).strip()
    return {"phase_line": phase, "state_updated": updated}


def _decisions_slot(root: Path) -> dict:
    env_dir = root / "envelopes"
    accepted = []
    if env_dir.is_dir():
        accepted = sorted(p.stem for p in env_dir.glob("*.json"))
    tasks_dir = root / "tasks"
    tasks = sorted(p.name for p in tasks_dir.iterdir() if p.is_dir()) if tasks_dir.is_dir() else []
    return {"accepted_envelopes": len(accepted), "envelope_ids": accepted[:8],
            "task_inventory": tasks}


def _linecount(p: Path) -> int:
    try:
        return sum(1 for _ in p.read_text(encoding="utf-8", errors="replace").splitlines())
    except Exception:
        return 0


def _approx_tokens(packet_bytes: int) -> int:
    return packet_bytes // 4


def boot(root: str | Path, *, budget: int = 1500,
         focus: str = "") -> BootPacket:
    root = Path(root)
    if not root.is_dir():
        return BootPacket(envelope_id="boot_missing", workspace_root=str(root),
                          root_hash="", git_head=None, context_budget=budget,
                          packet_tokens_approx=0, system={},
                          failure_code="missing_root", verdict="UNVERIFIABLE")
    files = _manifest(root)
    if not files:
        return BootPacket(envelope_id="boot_empty", workspace_root=str(root),
                          root_hash="", git_head=None, context_budget=budget,
                          packet_tokens_approx=0, system=_system_slot(root),
                          failure_code="empty_workspace", verdict="UNVERIFIABLE")
    rh = _root_hash(files, root)
    gh = _git_head(root)
    system = _system_slot(root)
    goals = _goals_slot(root)
    decisions = _decisions_slot(root)
    refs = []
    for i, p in enumerate(files):
        rel = p.relative_to(root).as_posix()
        refs.append(SourceRef(
            id=f"src_{i:03d}", path=rel, content_hash=_sha_file(p),
            bytes=p.stat().st_size, lines=_linecount(p),
            expansion=f"read {rel}"))
    pkt = BootPacket(
        envelope_id=f"boot_{rh}", workspace_root=str(root), root_hash=rh,
        git_head=gh, context_budget=budget, packet_tokens_approx=0,
        system=system, source_refs=refs,
        summary={**goals, **decisions, "source_files": len(files), "focus": focus},
        receipt_chain=[{"stage": "boot", "root_hash": rh, "git_head": gh}],
        failure_code=None, verdict="MATCH")
    pkt.packet_tokens_approx = _approx_tokens(len(str(pkt.to_dict()).encode()))
    while pkt.packet_tokens_approx > budget and len(pkt.source_refs) > 8:
        pkt.source_refs.pop()
        pkt.packet_tokens_approx = _approx_tokens(len(str(pkt.to_dict()).encode()))
    if pkt.packet_tokens_approx > budget:
        pkt.failure_code = "budget_exceeded"
        pkt.verdict = "DRIFT"
    return pkt


def verify_boot(packet: BootPacket, root: str | Path) -> str:
    root = Path(root)
    if not root.is_dir():
        return "UNVERIFIABLE"
    files = _manifest(root)
    if not files:
        return "UNVERIFIABLE"
    return "MATCH" if _root_hash(files, root) == packet.root_hash else "DRIFT"


def hydrate_prompt(packet: BootPacket, prompt: str) -> str:
    if packet.verdict != "MATCH":
        return prompt
    s = packet.summary
    head = (f"[ground] phase={s.get('phase_line','?')[:80]} "
            f"files={s.get('source_files',0)} accepted={s.get('accepted_envelopes',0)} "
            f"root_hash={packet.root_hash} modules={','.join(packet.system.get('harness_modules', [])[:6])}")
    return f"{head}\n\n{prompt}"
