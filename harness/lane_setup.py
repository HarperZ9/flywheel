"""The setup items a lane card states, each from a real check.

Every item the tool policy names in ``needs`` (``lane_tool_policy.SETUP_ITEMS``)
is evaluated here, once per request, from the mechanism that decides it:

- ``node`` and ``git``: ``tool_discovery`` (the operator's choice, the bundled
  runtime, the registry PATH, Program Files);
- ``model_server``: ``local_agent.health_report`` tiers at the two fixed local
  addresses, never ``OLLAMA_HOST``;
- ``project_folder``: the picked folder, refused inside the Flywheel home
  (``lane_runtime_frozen.local_model_root``). Only a frozen build launches
  local-model on it (``--mcp --root``); a pip or source install runs in the
  engine's workspace, so the item is met there and the card leaves it out;
- ``canon_blocks``: the blocks folder exists and holds N ``*.json`` blocks;
- ``provider_key``: three facts per granted name. Granted (``env_allow`` in
  lanes.json), present (the environment or the keychain holds a non-empty
  value; the check returns where it would come from, never the value), and
  validated only after one bound call succeeded;
- ``bulletin_identity``: a saved identity (registration is not checked here);
- ``writing_draft``: revision bodies recorded in the writing artifact store under
  ``<home>/state`` (counted by file, nothing is opened or created);
- ``claude_cli``: the claude CLI found by ``claude_discovery`` (the engine
  passes its path to articulate); whether it is signed in is not checked, and
  the copy says so.

Copy states the real steps a person takes. No item reads a key value into a
response or a log.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from .lane_tool_policy import SETUP_ITEMS, lane_policy
from .lane_workdir import flywheel_home, lane_workdir

SCHEMA = "flywheel.lane-setup/v1"
MODEL_HEALTH_TTL_S = 15.0
#: Lanes whose key-backed tools sit outside the build's main path; the card
#: names the key item for them even though no admitted tool needs it.
KEY_BACKED = {"forum": "Real rooms", "mneme": "Key-backed extraction"}
NODE_MISSING = ("Install Node.js 20 or later, or choose node.exe. "
                "Restart Flywheel after installing.")
GIT_MISSING = "Install Git for Windows to read branch and history."
_ROOT_COPY = {
    "local_model_root_unset": "Choose a project folder.",
    "local_model_root_missing": "The chosen project folder is gone. Choose a project folder.",
    "local_model_root_protected": ("Choose a project folder outside the Flywheel home and "
                                   "your home folder; the local agent refuses those."),
}


@dataclass(frozen=True)
class SetupItem:
    """One setup item as the card states it. ``facts`` never holds a secret."""
    id: str
    met: bool
    title: str
    copy: str
    facts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


_HEALTH: dict[str, object] = {}
_HEALTH_LOCK = threading.Lock()


def cached_model_health() -> dict:
    """``local_agent.health_report()``, reused for ``MODEL_HEALTH_TTL_S``."""
    with _HEALTH_LOCK:
        at = _HEALTH.get("at")
        if isinstance(at, float) and time.monotonic() - at < MODEL_HEALTH_TTL_S:
            return dict(_HEALTH["report"])  # type: ignore[arg-type]
    from .local_agent import health_report
    report = health_report()
    with _HEALTH_LOCK:
        _HEALTH.update(at=time.monotonic(), report=report)
    return dict(report)


def _default_node(environ: Mapping[str, str]):
    from . import node_lanes
    from .tool_discovery import find_node
    return find_node(environ, bundled=node_lanes.bundled_node(node_lanes.frozen_stage_root()))


def _default_git(environ: Mapping[str, str]):
    from .tool_discovery import find_git
    return find_git(environ)


def _default_claude(environ: Mapping[str, str]):
    from .claude_discovery import find_claude
    return find_claude(environ)


def _default_key_source(name: str) -> str:
    from .keychain import credential_source
    return credential_source(name)


def _default_key_grants(lane: str) -> tuple[str, ...]:
    from .lane_credentials import lane_key_grants
    return lane_key_grants(lane)


def _default_validated(lane: str) -> set[str]:
    from .lane_probe_cache import default_cache
    return default_cache().validated(lane)


class SetupChecks:
    """The seams every item reads through; tests replace them with fakes."""

    def __init__(self, environ: Mapping[str, str] | None = None, *,
                 node: Callable | None = None, git: Callable | None = None,
                 model_health: Callable[[], dict] | None = None,
                 key_source: Callable[[str], str] | None = None,
                 key_grants: Callable[[str], tuple] | None = None,
                 validated_keys: Callable[[str], set] | None = None,
                 frozen: bool | None = None, claude: Callable | None = None) -> None:
        self.environ = dict(os.environ) if environ is None else environ
        self.frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        self.node = node or (lambda: _default_node(self.environ))
        self.git = git or (lambda: _default_git(self.environ))
        self.claude = claude or (lambda: _default_claude(self.environ))
        self.model_health = model_health or cached_model_health
        self.key_source = key_source or _default_key_source
        self.key_grants = key_grants or _default_key_grants
        self.validated_keys = validated_keys or _default_validated
        self._memo: dict[tuple[str, str], SetupItem] = {}

    def item(self, item_id: str, lane: str) -> SetupItem:
        key = (item_id, lane if item_id == "provider_key" else "")
        if key not in self._memo:
            self._memo[key] = _EVALUATORS.get(item_id, _unmet_by_build)(self, lane, item_id)
        return self._memo[key]


def _item(item_id: str, met: bool, copy: str, **facts) -> SetupItem:
    return SetupItem(item_id, met, SETUP_ITEMS.get(item_id, item_id), copy, facts)


def _node(checks: SetupChecks, _lane: str, item_id: str) -> SetupItem:
    found = checks.node()
    facts = {"path": found.path, "version": found.version, "source": found.source}
    if found.found:
        return _item(item_id, True, f"Node {found.version} at {found.path}.", **facts)
    return _item(item_id, False, NODE_MISSING, **facts)


def _git(checks: SetupChecks, _lane: str, item_id: str) -> SetupItem:
    found = checks.git()
    facts = {"path": found.path, "source": found.source}
    if found.found:
        return _item(item_id, True, f"Git at {found.path}.", **facts)
    return _item(item_id, False, GIT_MISSING, **facts)


def _model_server(checks: SetupChecks, _lane: str, item_id: str) -> SetupItem:
    from .local_agent import OLLAMA_URL, SERVE_URL
    report = checks.model_health()
    tiers = [{"backend": str(t.get("backend", "")), "healthy": bool(t.get("healthy"))}
             for t in report.get("tiers", []) if isinstance(t, dict)]
    live = [t["backend"] for t in tiers if t["healthy"]]
    if live:
        return _item(item_id, True, f"Model server answering: {', '.join(live)}.", tiers=tiers)
    ollama, serve = (u.split("://", 1)[-1] for u in (OLLAMA_URL, SERVE_URL))
    return _item(item_id, False, f"Start a model server: Ollama with a pulled model at "
                 f"{ollama}, or a server at {serve}.", tiers=tiers)


def _project_folder(checks: SetupChecks, _lane: str, item_id: str) -> SetupItem:
    from .lane_runtime_frozen import local_model_root
    if not checks.frozen:
        return _item(item_id, True, "Runs in the engine's workspace; the installed app "
                     "asks for a project folder.", root=None, code="not_frozen")
    root, code = local_model_root(checks.environ)
    if root:
        return _item(item_id, True, f"Project folder: {root}.", root=root, code="")
    return _item(item_id, False, _ROOT_COPY.get(code, _ROOT_COPY["local_model_root_unset"]),
                 root=None, code=code)


def _canon_blocks(checks: SetupChecks, _lane: str, item_id: str) -> SetupItem:
    raw = checks.environ.get("CANON_BLOCKS_DIR")
    folder = Path(raw) if raw else lane_workdir("canon", checks.environ) / "blocks"
    exists = folder.is_dir()
    count = len(list(folder.glob("*.json"))) if exists else 0
    facts = {"folder": str(folder), "exists": exists, "count": count}
    if count:
        return _item(item_id, True, f"{count} blocks in {folder}.", **facts)
    return _item(item_id, False, f"Put blocks in {folder}.", **facts)


def _provider_key(checks: SetupChecks, lane: str, item_id: str) -> SetupItem:
    names = tuple(checks.key_grants(lane))
    validated = checks.validated_keys(lane) if names else set()
    keys = [{"name": n, "granted": True, "present": checks.key_source(n) in ("env", "keychain"),
             "validated": n in validated} for n in names]
    purpose = KEY_BACKED.get(lane, "This lane")
    lanes_json = flywheel_home(checks.environ) / "lanes.json"
    if not keys:
        return _item(item_id, False, (
            f"{purpose} need a provider key. Save the key in the Keys panel on the Endpoints "
            f"screen, add its name to this lane's env_allow in {lanes_json}, restart Flywheel."),
            keys=[], lanes_json=str(lanes_json))
    facts = "; ".join(
        f"{k['name']}: granted, {'present' if k['present'] else 'not present'}, "
        f"{'validated' if k['validated'] else 'not validated'}" for k in keys)
    return _item(item_id, any(k["present"] for k in keys),
                 f"{purpose} need a provider key: {facts}.", keys=keys,
                 lanes_json=str(lanes_json))


def _bulletin_identity(checks: SetupChecks, _lane: str, item_id: str) -> SetupItem:
    from .bulletin_identity_contract import BULLETIN_CREDENTIAL_NAME
    saved = checks.key_source(BULLETIN_CREDENTIAL_NAME) in ("env", "keychain")
    if saved:
        return _item(item_id, True, "Identity saved. Registration with the board is not "
                     "checked here.", saved=True)
    return _item(item_id, False, "Create and register an identity in the Keys panel on the "
                 "Endpoints screen.", saved=False)


def _writing_draft(checks: SetupChecks, _lane: str, item_id: str) -> SetupItem:
    store = flywheel_home(checks.environ) / "state" / "artifacts" / "writing" / "v1"
    count = len(list(store.glob("owners/*/projects/*/body/*.txt"))) if store.is_dir() else 0
    if count:
        return _item(item_id, True, f"{count} draft revisions recorded.", count=count)
    return _item(item_id, False, "Record a draft on the Writing screen first.", count=0)


def _claude_cli(checks: SetupChecks, _lane: str, item_id: str) -> SetupItem:
    found = checks.claude()
    facts = {"path": found.path, "source": found.source}
    if found.found:
        return _item(item_id, True, f"claude CLI at {found.path}. It must be signed in "
                     "(run claude login); that is not checked here.", **facts)
    return _item(item_id, False, "Install the claude CLI and run claude login, or set "
                 "ARTICULATE_CLAUDE_CLI to its full path. Restart Flywheel after "
                 "installing.", **facts)


def _unmet_by_build(_checks: SetupChecks, lane: str, item_id: str) -> SetupItem:
    return _item(item_id, False, "Not available in this build.")


_EVALUATORS = {"node": _node, "git": _git, "model_server": _model_server,
               "project_folder": _project_folder, "canon_blocks": _canon_blocks,
               "provider_key": _provider_key, "bulletin_identity": _bulletin_identity,
               "writing_draft": _writing_draft, "claude_cli": _claude_cli}


def lane_needs(lane: str, *, frozen: bool | None = None) -> list[str]:
    """Setup item ids the lane's in-build tools need, in table order, plus the
    key item for a key-backed lane. ``project_folder`` applies to a frozen
    build only (C16)."""
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    needs: dict[str, None] = {}
    for entry in lane_policy(lane).values():
        if not entry.not_in_build:
            needs.update(dict.fromkeys(entry.needs))
    if lane in KEY_BACKED:
        needs["provider_key"] = None
    if not frozen:
        needs.pop("project_folder", None)
    return list(needs)


def lane_setup(lane: str, checks: SetupChecks | None = None) -> dict:
    """Every setup item this lane's card states, met or not."""
    checks = checks or SetupChecks()
    items = [checks.item(item_id, lane) for item_id in lane_needs(lane, frozen=checks.frozen)]
    return {"schema": SCHEMA, "lane": lane, "items": [i.to_dict() for i in items],
            "unmet": [i.id for i in items if not i.met]}
