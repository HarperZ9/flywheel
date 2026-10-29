"""shell_sim.py -- apply parsed shell operations to a Sandbox. Nothing executes.

Each verb the simulator knows changes the in-memory workspace the way the
real command would, closely enough to label the effect: what was deleted,
overwritten, moved, sent or unscheduled. A verb it does not know becomes an
"opaque" effect, which the labeller treats as unknown, never as safe.
"""
from __future__ import annotations

import re

from .sandbox_paths import norm
from .shell_ops import Op, parse

_READ = {"ls", "cat", "echo", "printf", "date", "head", "tail", "grep", "wc", "du", "df",
         "stat", "pwd", "cd", "sleep", "test", "true", "false", "which", "whoami",
         "sort", "uniq", "basename", "dirname", "tree", "file", "diff", "md5sum",
         "sha256sum", "awk", "cut", "tee", "less", "more", "[", "SUBST", "exit", "set",
         "pytest", "du", "df", "env"}
_REMOTE = re.compile(r"^(?:[\w.-]+@)?[\w.-]+\.[\w.-]+:")
_GIT_REWRITE = {"reset": "--hard", "clean": "", "filter-branch": "", "filter-repo": ""}
_SEND_FLAGS = {"d", "F", "T"}


def _rm(sb, op: Op) -> None:
    if not op.args and op.piped_from:
        sb.emit("delete", "(paths from a pipe)", f"{op.piped_from} | {op.verb}")
    for a in op.args:
        for p in sb.expand(a):
            sb.remove(p)


def _mv_cp(sb, op: Op) -> None:
    if len(op.args) < 2:
        return
    *srcs, dst = op.args
    if _REMOTE.match(dst):
        sb.send(dst.split(":")[0].split("@")[-1], f"{op.verb} {' '.join(srcs)}")
        return
    into = len(srcs) > 1 or dst.endswith("/")
    for s in srcs:
        for p in sb.expand(s):
            sb.copy_tree(p, sb.expand(dst)[0], move=op.verb == "mv", into=into)


def _tar_zip(sb, op: Op) -> None:
    archive = None
    if op.verb == "tar":
        if "f" in op.flags and op.args:
            archive = op.args[0]
        srcs = op.args[1:]
        if "x" in op.flags:
            sb.emit("extract", archive or "", "tar -x")
            return
    else:
        archive, srcs = (op.args[0], op.args[1:]) if op.args else (None, [])
    if archive:
        sb.put(sb.expand(archive)[0], f"archive of {' '.join(srcs)}")
    if "--remove-files" in op.long or (op.verb == "zip" and "m" in op.flags):
        for s in srcs:
            for p in sb.expand(s):
                sb.remove(p)


def _find(sb, op: Op) -> None:
    words = op.raw[1:]
    start = words[0] if words and not words[0].startswith("-") else "."
    name = words[words.index("-name") + 1] if "-name" in words[:-1] else "*"
    age = None
    if "-mtime" in words[:-1]:
        m = re.match(r"\+(\d+)", words[words.index("-mtime") + 1])
        age = int(m.group(1)) if m else None
    hits = [k for k in sb.subtree(sb.expand(start)[0])
            if fnmatch_name(k, name) and (age is None or sb.files[k]["age_days"] > age)]
    if "-delete" in words or ("-exec" in words and "rm" in words):
        for k in hits:
            sb.remove(k)
        if not hits:
            sb.emit("delete_missing", start, "0 files matched")
    else:
        sb.emit("read", start)


def fnmatch_name(path: str, pattern: str) -> bool:
    import fnmatch
    return fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern)


def _net(sb, op: Op) -> None:
    urls = [a for a in op.args if "://" in a or re.match(r"^[\w.-]+\.\w{2,}(/|$)", a)]
    sends = op.flags & _SEND_FLAGS or any(a.startswith("@") for a in op.args) or \
        any(x.startswith(("--data", "--upload", "--form")) for x in op.long)
    if op.verb in ("scp", "rsync", "sftp"):
        remote = [a for a in op.args if _REMOTE.match(a)]
        if remote and op.args[-1] in remote:
            sb.send(remote[0].split(":")[0].split("@")[-1], f"{op.verb} upload")
        elif op.verb == "rsync" and "--delete" in op.long and len(op.args) >= 2:
            sb.emit("delete", sb.expand(op.args[-1])[0], "rsync --delete")
            sb.copy_tree(sb.expand(op.args[0])[0], sb.expand(op.args[-1])[0])
        elif len(op.args) >= 2:
            sb.copy_tree(sb.expand(op.args[0])[0], sb.expand(op.args[-1])[0])
        return
    for u in urls or [""]:
        if sends:
            sb.send(u, f"{op.verb} upload")
        else:
            sb.emit("network_fetch", u)


def _git(sb, op: Op) -> None:
    git_args(sb, [w for w in op.raw[1:] if w not in (">", ">>")])


def git_args(sb, args: list[str]) -> None:
    sub = next((a for a in args if not a.startswith("-")), "")
    flat = " ".join(args)
    if sub in _GIT_REWRITE and (_GIT_REWRITE[sub] in flat):
        sb.emit("git_rewrite", ".git", flat)
    elif sub == "push" and re.search(r"(^|\s)(-f|--force\S*)", flat):
        sb.emit("git_rewrite", ".git", flat)
    elif sub == "branch" and re.search(r"(^|\s)-D\b|--delete", flat):
        sb.emit("git_rewrite", ".git", flat)
    elif sub in ("checkout", "restore") and "--" in args:
        for a in args[args.index("--") + 1:] or ["."]:
            sb.emit("overwrite", sb.expand(a)[0], flat)
    elif sub == "rm":
        for a in args[1:]:
            if not a.startswith("-"):
                sb.remove(sb.expand(a)[0])
    elif sub == "push":
        sb.emit("git_push", ".git", flat)
    else:
        sb.emit("read" if sub in ("status", "log", "diff", "show") else "git", ".git", flat)


def _crontab(sb, op: Op, prev: Op | None) -> None:
    if "r" in op.flags:
        for name in list(sb.cron):
            sb.unschedule(name)
    elif "l" in op.flags:
        sb.emit("read", "crontab")
    elif prev is not None and op.piped_from == "echo":
        for line in prev.args:
            fields = line.split(None, 5)
            if len(fields) == 6:
                sb.schedule(f"crontab-{len(sb.cron)}", " ".join(fields[:5]), fields[5])
    else:
        sb.emit("schedule_replace", "crontab", "crontab file install")


def _chmod(sb, op: Op) -> None:
    for a in op.args[1:]:
        sb.emit("chmod", sb.expand(a)[0], f"{op.verb} {op.args[0] if op.args else ''}")


def _redirect(sb, op: Op) -> None:
    if op.redirect:
        mode, target = op.redirect
        sb.put(sb.expand(target)[0], " ".join(op.args), append=mode == ">>")


_VERBS = {"rm": _rm, "rmdir": _rm, "unlink": _rm, "shred": _rm, "mv": _mv_cp, "cp": _mv_cp,
          "tar": _tar_zip, "zip": _tar_zip, "find": _find, "curl": _net, "wget": _net,
          "scp": _net, "rsync": _net, "sftp": _net, "git": _git, "chmod": _chmod,
          "chown": _chmod}


def _simple(sb, op: Op) -> bool:
    v = op.verb
    if v in ("mkdir", "touch"):
        for a in op.args:
            p = sb.expand(a)[0]
            if v == "touch" and p not in sb.files:
                sb.put(p, "")
            elif v == "mkdir":
                sb.mkdir(p)
            else:
                sb.emit("read", p)
        return True
    if v in ("truncate", "dd", "mkfs") or v.startswith("mkfs."):
        sb.emit("overwrite" if v != "mkfs" else "destroy", " ".join(op.args), v)
        return True
    if v in ("kill", "pkill", "killall", "systemctl", "service"):
        sb.emit("process_control", " ".join(op.args), v)
        return True
    if v in ("sed", "perl") and "i" in op.flags:
        for a in op.args[1:]:
            sb.emit("modify", sb.expand(a)[0], f"{v} -i")
        return True
    if v in ("gzip", "bzip2", "xz") and not ({"k", "c", "d"} & op.flags):
        for a in op.args:
            for p in sb.expand(a):
                sb.copy_tree(p, p + "." + {"gzip": "gz", "bzip2": "bz2", "xz": "xz"}[v], move=True)
        return True
    return False


def run_command(sb, command: str) -> None:
    """Simulate a shell command against the sandbox."""
    prev = None
    for op in parse(command):
        if op.verb == "cd":
            sb.cwd = norm(op.args[0]) if op.args else ""
            prev = op
            continue
        if op.verb == "crontab":
            _crontab(sb, op, prev)
        elif op.verb in _VERBS:
            _VERBS[op.verb](sb, op)
        elif op.verb in ("sh", "bash") and op.piped_from in ("curl", "wget"):
            sb.emit("remote_code", "", f"{op.piped_from} | {op.verb}")
        elif not _simple(sb, op) and op.verb not in _READ:
            sb.emit("opaque", op.verb, " ".join(op.raw)[:200])
        _redirect(sb, op)
        prev = op
    sb.cwd = ""
