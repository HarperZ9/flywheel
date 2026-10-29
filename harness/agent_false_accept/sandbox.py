"""sandbox.py -- an in-memory workspace, scheduler and network log.

Every tool call the agent makes lands here and nowhere else. The filesystem
is a dict of path -> file record, cron is a dict of name -> job, and the
network is a list the sandbox appends to. A call returns a short text result
for the agent and a list of effects for the labeller. A scheduled command is
also simulated, on a copy of the workspace, and its effects are marked
deferred: a cron job that deletes the backups tonight is a deletion now.
"""
from __future__ import annotations

import copy
import fnmatch
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .sandbox_paths import ROOT, norm  # noqa: F401  (norm is re-exported)
from .shell_sim import run_command


@dataclass
class Effect:
    kind: str           # read, create, modify, overwrite, delete, move, chmod, ...
    path: str = ""
    detail: str = ""
    deferred: bool = False

    def to_dict(self) -> dict:
        return {"kind": self.kind, "path": self.path, "detail": self.detail,
                "deferred": self.deferred}


@dataclass
class Sandbox:
    files: dict = field(default_factory=dict)   # path -> {"content", "age_days", "mode"}
    cron: dict = field(default_factory=dict)    # name -> {"schedule", "command"}
    network: list = field(default_factory=list)
    effects: list = field(default_factory=list)
    deferred: bool = False
    dirs: set = field(default_factory=set)     # empty directories made by mkdir
    cwd: str = ""                               # set by `cd` inside one shell command

    @classmethod
    def from_spec(cls, spec: dict) -> "Sandbox":
        files = {norm(k): {"content": v.get("content", ""), "age_days": v.get("age_days", 1),
                           "mode": v.get("mode", "644")} for k, v in spec["files"].items()}
        return cls(files=files, cron=copy.deepcopy(spec.get("cron", {})))

    # -- filesystem helpers used by the tool layer and the shell simulator --
    def emit(self, kind: str, path: str = "", detail: str = "") -> None:
        self.effects.append(Effect(kind, path, detail, self.deferred))

    def is_dir(self, p: str) -> bool:
        return p == "" or p in self.dirs or any(k.startswith(p + "/") for k in self.files)

    def mkdir(self, p: str) -> None:
        self.dirs.add(p)
        self.emit("create", p)

    def exists(self, p: str) -> bool:
        return p in self.files or self.is_dir(p)

    def subtree(self, p: str) -> list[str]:
        if p == "":
            return list(self.files)
        return [k for k in self.files if k == p or k.startswith(p + "/")]

    def expand(self, raw: str) -> list[str]:
        p = norm(raw)
        if self.cwd and not p.startswith("outside:") and not str(raw).strip().startswith(ROOT):
            base = self.cwd if self.cwd.startswith("outside:") else f"{ROOT}/{self.cwd}"
            p = norm(f"{base}/{p}") if not base.startswith("outside:") else f"{base}/{p}"
        if p.startswith("outside:") or not any(c in p for c in "*?["):
            return [p]
        names = set(self.files) | {k.rsplit("/", 1)[0] for k in self.files if "/" in k}
        hits = sorted(n for n in names if fnmatch.fnmatchcase(n, p))
        return hits or [p]

    def remove(self, p: str, why: str = "delete") -> int:
        if p.startswith("outside:"):
            self.emit(why, p, "outside workspace")
            return 0
        gone = self.subtree(p)
        for k in gone:
            del self.files[k]
        if not gone and p not in self.dirs and p != "":
            self.emit("delete_missing", p, "nothing there")   # an attempt that removes nothing
            return 0
        self.dirs = {d for d in self.dirs if not (d == p or d.startswith(p + "/"))}
        self.emit(why, p if p else ".", f"{len(gone)} files")
        return len(gone)

    def put(self, p: str, content: str, append: bool = False) -> None:
        if p.startswith("outside:"):
            if p != "outside:/dev/null":
                self.emit("write_outside", p)
            return
        if p in self.files:
            self.emit("modify" if append else "overwrite", p)
            old = self.files[p]["content"] if append else ""
            self.files[p] = {**self.files[p], "content": old + content, "age_days": 0}
        else:
            self.emit("create", p)
            self.files[p] = {"content": content, "age_days": 0, "mode": "644"}

    def copy_tree(self, src: str, dst: str, move: bool = False, into: bool = False) -> None:
        items = self.subtree(src)
        if not items:
            self.emit("read", src, "missing")
            return
        if (into or self.is_dir(dst)) and dst not in self.files:
            dst = (dst + "/" if dst else "") + src.rsplit("/", 1)[-1]
        for k in items:
            target = dst + k[len(src):]
            if target in self.files and target != k:
                self.emit("overwrite", target, f"by {'move' if move else 'copy'}")
            self.files[target] = dict(self.files[k])
        if move:
            for k in items:
                if not (k + "/").startswith(dst + "/"):
                    self.files.pop(k, None)
            self.emit("move", src, f"to {dst}")
        else:
            self.emit("create", dst, f"copy of {src}")

    def send(self, url: str, detail: str) -> None:
        host = urlparse(url if "://" in url else "https://" + url).hostname or url
        self.network.append({"host": host, "detail": detail})
        self.emit("network_send", host, detail)

    def schedule(self, name: str, schedule: str, command: str) -> None:
        if name in self.cron:
            self.emit("schedule_replace", name, self.cron[name]["command"][:120])
        else:
            self.emit("schedule_add", name, schedule)
        self.cron[name] = {"schedule": schedule, "command": command}
        shadow = Sandbox(files=copy.deepcopy(self.files), cron=copy.deepcopy(self.cron),
                         deferred=True)
        run_command(shadow, command)
        self.effects.extend(shadow.effects)

    def unschedule(self, name: str) -> None:
        if self.cron.pop(name, None) is None:
            self.emit("read", name, "no such cron job")
        else:
            self.emit("schedule_remove", name)
