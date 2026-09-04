"""authority_registry.py -- authorities as data, so a contract can travel.

`output_contract` takes authorities as Python callables, which is right for a
library and useless for a task written in JSON. This turns a declaration into
one of those callables.

Three kinds, split by what each is able to decide:

    citation   decides nothing, and only asks that the answer name a source
    table      decides by lookup in a file that shipped with the task
    command    decides by running a program that is not the one being checked

`command` is the general case and the one with teeth. A check is worth
something only when the thing deciding is not the thing that produced the
answer, and a separate process is the plainest way to guarantee that. It is
also an execution surface, so it stays off unless the caller turns it on, and a
contract that needs it without the grant comes back unverified rather than
passed.

Failing toward unverified is the design. A check nobody could run must never
read as a check that passed.

The command protocol, which is the whole contract a checker program has to
meet:

    stdin      the answer, as JSON
    stdout     {"value": <the authoritative value>}, as JSON
    exit 0     the value on stdout decides this field
    exit 3     this input is outside what the program covers, decline it
    anything   the program broke, and the field goes unchecked

Exit 3 exists so a program can decline without being mistaken for a crash.
Those are different facts and a contract that merges them will publish a
guess.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

CITATION = "citation"
TABLE = "table"
COMMAND = "command"
KINDS = (CITATION, TABLE, COMMAND)

DECLINED = 3
DEFAULT_TIMEOUT_SECONDS = 30.0


class AuthorityError(ValueError):
    """Raised on a declaration that could not describe a working authority."""


def _claimed(answer: dict, name: str):
    return ((answer or {}).get(name) or {}).get("value")


def _citation_resolver(_spec, _base, _allow, _timeout):
    """Never consulted for a value. `output_contract` short-circuits a CITED
    field before it resolves anything, and this exists so the source still has
    to be declared rather than being implied by its absence."""
    def resolve(_answer):
        raise LookupError("a citation authority decides no value")
    return resolve


def _table_resolver(spec, base: Path, _allow, _timeout):
    """A JSON object of key to value, read on first use.

    Read lazily so a missing or malformed file lands as one unchecked field
    rather than as a crash that discards every other field's verdict. The path
    and the parse error both survive into the report.
    """
    path = base / spec["path"]
    key_field = spec["key_field"]
    cache: dict = {}

    def resolve(answer):
        if not cache:
            cache["rows"] = json.loads(path.read_text(encoding="utf-8"))
        key = _claimed(answer, key_field)
        if key is None:
            raise LookupError(f"the answer states no {key_field} to look up")
        text = str(key)
        rows = cache["rows"]
        if text not in rows:
            raise LookupError(f"{path.name} does not list {text!r}")
        return rows[text]

    return resolve


def _command_resolver(spec, base: Path, allow: bool, timeout: float):
    argv = [str(part) for part in spec["argv"]]

    def resolve(answer):
        if not allow:
            raise PermissionError(
                "command authorities are not granted for this run, so this "
                "field is unchecked rather than confirmed")
        # The answer goes on stdin, never in argv. Arguments are readable by
        # every process on the machine and an answer is the caller's data.
        done = subprocess.run(argv, input=json.dumps(answer), capture_output=True,
                              text=True, timeout=timeout, shell=False, cwd=base,
                              check=False)
        if done.returncode == DECLINED:
            raise LookupError(done.stderr.strip() or "the authority declined this input")
        if done.returncode != 0:
            raise RuntimeError(f"exit {done.returncode}: {done.stderr.strip()[:200]}")
        return json.loads(done.stdout)["value"]

    return resolve


_BUILDERS = {CITATION: _citation_resolver, TABLE: _table_resolver,
             COMMAND: _command_resolver}
_REQUIRED = {CITATION: (), TABLE: ("path", "key_field"), COMMAND: ("argv",)}


def build_authorities(declarations: dict, *, allow_commands: bool = False,
                      base_dir=None, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Declared authorities, as the callables `check_answer` expects.

    Structure is checked here and failures at that level raise, because a
    misspelled kind is the contract author's mistake and hiding it as an
    unchecked field would let a contract quietly stop checking anything.
    Everything that can only fail later, at the moment the authority runs,
    fails there instead and becomes an unchecked field.
    """
    base = Path(base_dir or ".").resolve()
    resolvers = {}
    for source, spec in (declarations or {}).items():
        if not isinstance(spec, dict):
            raise AuthorityError(f"{source}: a declaration must be an object")
        kind = spec.get("kind")
        if kind not in KINDS:
            raise AuthorityError(f"{source}: unknown kind {kind!r}")
        missing = [key for key in _REQUIRED[kind] if not spec.get(key)]
        if missing:
            raise AuthorityError(f"{source}: {kind} needs {', '.join(missing)}")
        resolvers[source] = _BUILDERS[kind](spec, base, allow_commands, timeout)
    if not resolvers:
        raise AuthorityError("a contract with no authorities checks nothing")
    return resolvers
