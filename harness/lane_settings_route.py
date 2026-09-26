"""The two setup choices a person makes for the lanes, each a granted action.

- ``/api/lanes/local-model/root`` (action ``lane.root``): the project folder the
  local model lane runs in. It widens what a T1 ``local_agent_run`` reads, so a
  bearer token alone does not choose it. Refused inside the Flywheel home or as
  the home folder itself.
- ``/api/settings/node_path`` (action ``settings.node_path``): the ``node``
  executable the Node lanes run. It picks what the engine executes, so it takes
  the same kind of grant as ``plugin.register`` (security finding S3,
  POLICY-DECISION C-15). Only an absolute path to a file named ``node.exe`` on
  Windows (``node`` elsewhere) is accepted, never ``node.cmd`` or ``node.bat``,
  which CreateProcess would run through cmd.exe. The file's sha256 is saved with
  the path, and ``tool_discovery`` checks it again before every launch, so a
  replaced file is not run under the old choice.

A POST reaches these functions only after the gateway consumed an exact grant
for the action (``gateway_operation.action_for_path``); the body is the
approved operation. GET answers the current item with no grant.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable, Mapping

NODE_PATH_ROUTE = "/api/settings/node_path"
LOCAL_MODEL_ROOT_ROUTE = "/api/lanes/local-model/root"
SETTING_FIELDS = {
    "settings.node_path": ({"data_refs", "credential_refs"}, {"path"}),
    "lane.root": ({"data_refs", "credential_refs"}, {"path"}),
}
SETTING_PATHS = {NODE_PATH_ROUTE: "settings.node_path", LOCAL_MODEL_ROOT_ROUTE: "lane.root"}
SETTING_DESTINATIONS = {"settings.node_path": {"kind": "setting", "ref": "node_path"},
                        "lane.root": {"kind": "lane", "ref": "local-model/root"}}
SETTING_SCOPES = {"settings.node_path": ("write", "exec"), "lane.root": ("write",)}


def _bad(reason: str, status: int = 400) -> tuple[dict, int]:
    return {"code": "INVALID_REQUEST", "error": "the request is invalid",
            "reason": reason}, status


def root_body(environ: Mapping[str, str]) -> dict:
    from .lane_setup import SetupChecks
    # the picked folder itself, as the installed app launches on it
    return SetupChecks(environ, frozen=True).item("project_folder", "local-model").to_dict()


def root_post(req: Mapping[str, object], environ: Mapping[str, str]) -> tuple[dict, int]:
    """Write or clear ``<home>/lanes/local-model/root`` after the start rule."""
    from .lane_runtime_frozen import local_model_root_file
    from .lane_workdir import ensure_lane_workdir
    raw = req.get("path")
    target = local_model_root_file(environ)
    if raw in (None, ""):
        target.unlink(missing_ok=True)
        return root_body(environ), 200
    if not isinstance(raw, str) or "\x00" in raw:
        return _bad("path_not_a_string")
    folder = Path(os.path.expanduser(raw.strip()))
    if not folder.is_absolute() or not folder.is_dir():
        return _bad("local_model_root_missing")
    from .local_agent_grants import GrantRefusal, grants_from_config
    try:
        grants_from_config(environ, workspace=str(folder))
    except GrantRefusal:
        return _bad("local_model_root_protected", 409)
    ensure_lane_workdir("local-model", environ)
    target.write_text(str(folder) + "\n", encoding="utf-8")
    return root_body(environ), 200


def node_path_get(environ: Mapping[str, str] | None = None) -> dict:
    env = os.environ if environ is None else environ
    from .lane_setup import SetupChecks
    body = SetupChecks(env).item("node", "learn").to_dict()
    body["override"] = bool(env.get("FLYWHEEL_NODE"))
    return body


def node_executable_name(platform: str = os.name) -> str:
    return "node.exe" if platform == "nt" else "node"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def node_path_post(req: Mapping[str, object], environ: Mapping[str, str] | None = None,
                   *, version_probe: Callable[[str], str | None] | None = None,
                   platform: str = os.name) -> tuple[dict, int]:
    """Write or clear ``<home>/node_path``: the resolved path and its sha256."""
    from .lane_workdir import flywheel_home
    from .tool_discovery import MIN_NODE_MAJOR, NODE_PATH_FILE, node_major, node_version
    env = os.environ if environ is None else environ
    target = flywheel_home(env) / NODE_PATH_FILE
    raw = req.get("path")
    if raw in (None, ""):
        target.unlink(missing_ok=True)
        return node_path_get(env), 200
    if not isinstance(raw, str) or "\x00" in raw:
        return _bad("path_not_a_string")
    given = Path(raw.strip().strip('"'))
    if not given.is_absolute():
        return _bad("path_not_absolute")
    path = given.resolve()
    if not path.is_file() or path.name.lower() != node_executable_name(platform):
        return _bad("not_a_node_executable")
    major = node_major((version_probe or node_version)(str(path)))
    if major is None or major < MIN_NODE_MAJOR:
        return _bad("node_too_old_or_silent")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{path}\nsha256={file_sha256(path)}\n", encoding="utf-8")
    return node_path_get(env), 200


def setting_post(path: str, req: Mapping[str, object] | None,
                 environ: Mapping[str, str] | None = None) -> tuple[dict, int]:
    """Serve one granted setting POST with the approved operation as its body."""
    env = os.environ if environ is None else environ
    body = dict(req or {})
    if path == LOCAL_MODEL_ROOT_ROUTE:
        return root_post(body, env)
    return node_path_post(body, env)
