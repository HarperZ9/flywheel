"""sandbox_protected_paths.py -- the files a confined command may not read.

Neither POSIX backend confines reads. `--ro-bind / /` is a write barrier, and
the Seatbelt profile opens with `(allow default)`, so a command running under
either one can open `~/.ssh/id_ed25519` and print it. That is stated in
`posix_sandbox` and it is true, and it is also worse than it needs to be.

Confining reads properly means enumerating every path a toolchain may open,
which is the large piece of work that docstring declines. Naming the small set
it may NOT open is a different job and a much smaller one, and it removes the
targets worth stealing. Claude Code ships a protected-path list for the same
reason. Cursor goes further on Linux, where Landlock can deny reads by
default; bubblewrap has no such primitive and can only mount over a path.

THIS IS A DENYLIST AND A DENYLIST IS NOT CONFINEMENT. A credential kept
somewhere not named here stays readable, and no field anywhere should say
otherwise: `READS_CONFINED` stays False on both backends, and what these
paths buy is recorded under its own name.

Two mechanisms, because the backends have two:

  seatbelt  `(deny file-read-data (subpath ...))` after `(allow default)`,
            the same last-match-wins ordering the write rules already use.
            Metadata reads stay allowed on purpose. Denying those as well
            would break `ls ~` for a gain that is close to nothing, since
            these path names are public knowledge.

  bwrap     an empty mount over the path. A directory gets a tmpfs and a file
            gets `/dev/null` bound read-only. The tmpfs is writable and it
            dies with the namespace, exactly like the `--tmpfs /tmp` the argv
            already carries, so a write there never reaches the host and the
            `writes confined to` line stays true.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

#: Directories whose whole purpose is credentials. Hiding one of these breaks
#: the tool that reads it, which is the intent: a confined command has no
#: business spending the operator's cloud or git identity.
CREDENTIAL_DIRECTORIES = (
    ".ssh", ".aws", ".azure", ".gnupg", ".kube",
    ".config/gh", ".config/gcloud", ".flywheel/keys",
)

#: Credential files that live inside general-purpose directories. Named one by
#: one rather than by their parent, because hiding `~/.docker` or `~/.config`
#: would take non-credential state with it.
CREDENTIAL_FILES = (
    ".netrc", ".npmrc", ".pypirc", ".git-credentials",
    ".docker/config.json",
)


def default_paths(home) -> tuple:
    """The protected set for one home directory, as (kind, path) pairs.

    Paths are returned whether or not they exist. Neither mechanism needs the
    path to be there, and stat-ing the host would make the argv depend on the
    machine that built it, which is the property that lets a Windows checkout
    assert what a Linux run will do.
    """
    base = PurePosixPath(str(home).replace("\\", "/"))
    return (tuple(("dir", (base / name).as_posix())
                  for name in CREDENTIAL_DIRECTORIES)
            + tuple(("file", (base / name).as_posix())
                    for name in CREDENTIAL_FILES))


def present_paths(home, exists=None) -> tuple:
    """The protected set narrowed to what this host actually has.

    A path that is not there buys nothing by being hidden, and on Linux it
    costs something. Every hide is a mount, bubblewrap has to create the
    mount point, and the destination's parent sits on a read-only bind, so a
    mount over a path that does not exist can fail and take the whole run
    down with it. Hiding what is there removes that failure mode, and it
    keeps the record to paths that were really covered.

    `exists` is injectable, so the filter is assertable from a host that has
    none of these paths.
    """
    look = exists if exists is not None else (lambda path: Path(path).exists())
    return tuple(pair for pair in default_paths(home) if look(pair[1]))


def sbpl_deny_lines(paths, quote) -> list:
    """Seatbelt rules denying the contents of each protected path.

    `quote` is the caller's path-to-policy-text function, so a path that
    cannot be written into a profile refuses here in the same way and for the
    same reason it refuses everywhere else.
    """
    if not paths:
        return []
    lines = ["(deny file-read-data"]
    for kind, path in paths:
        keyword = "subpath" if kind == "dir" else "literal"
        lines.append(f'  ({keyword} "{quote(path)}")')
    lines[-1] += ")"
    return lines


def bwrap_hide_args(paths) -> list:
    """bubblewrap arguments mounting an empty filesystem over each path.

    Emitted last by the caller so they layer over every earlier bind. A
    protected path that falls inside the writable workspace is hidden anyway,
    which is the right way round: the protection is the stronger claim.
    """
    argv = []
    for kind, path in paths:
        if kind == "dir":
            argv += ["--tmpfs", path]
        else:
            argv += ["--ro-bind", "/dev/null", path]
    return argv
