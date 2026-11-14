"""tool_specs.py -- the session's tools as JSON schemas, for native function calling.

The session describes its tools to a model twice. Every model gets the text
protocol lines in the system prompt (`TOOL name {json}`). A provider with a
function-calling interface also gets the list built here: the same tools, the
same argument names, as JSON Schema objects.

A schema here adds no tool and grants nothing. The executor decides what a
call may do, exactly as it does for a call written as a TOOL line.

Only a name made of letters, digits and underscores, at most 64 long, is
offered. That is the set every provider accepts and the set the text protocol
can carry, so a tool with another name stays reachable the way it was before:
not at all through a TOOL line.
"""
from __future__ import annotations

import re

NAME = re.compile(r"^[A-Za-z0-9_]{1,64}$")
OPEN = {"type": "object", "properties": {}, "additionalProperties": True}


def _obj(required: tuple = (), **properties) -> dict:
    return {"type": "object", "properties": properties, "required": list(required)}


_STR, _INT = {"type": "string"}, {"type": "integer"}
_AGENT_CALL = _obj(("agent", "prompt"), agent=_STR, prompt=_STR)
_TODO_ITEM = _obj(("text",), text=_STR,
                  status={"type": "string", "enum": ["pending", "in_progress", "done"]})

BUILTIN = {
    "repo_map": ("Outline the files and symbols under a folder of the project.",
                 _obj(path=_STR)),
    "read_file": ("Read a file in the project. The result starts with READ_FILE_META, which "
                  "gives next_offset and identity. While truncated is true, read on with "
                  "offset=next_offset and if_identity=identity.",
                  _obj(("path",), path=_STR, offset=_INT, max_bytes=_INT,
                       if_identity={"type": "object"})),
    "list_dir": ("List the entries of a folder in the project.", _obj(path=_STR)),
    "grep": ("Search file contents with a regular expression. Returns path:line:text.",
             _obj(("pattern",), pattern=_STR, path=_STR, glob=_STR)),
    "glob": ("List project paths that match a glob pattern such as **/*.py.",
             _obj(("pattern",), pattern=_STR)),
    "edit_file": ("Replace one exact piece of text in a file. The old text must occur "
                  "exactly once.", _obj(("path", "old", "new"), path=_STR, old=_STR, new=_STR)),
    "write_file": ("Write a whole file, creating or replacing it.",
                   _obj(("path", "content"), path=_STR, content=_STR)),
    "apply_patch": ("Apply a unified diff to files in the project.",
                    _obj(("patch",), patch=_STR)),
    "run": ("Run a shell command in the project folder and return its exit code and output.",
            _obj(("cmd",), cmd=_STR)),
    "run_background": ("Start a long command, such as a dev server or a watcher, and return "
                       "a job id.", _obj(("cmd",), cmd=_STR)),
    "processes": ("List background jobs, read one job's output, or stop it.",
                  _obj(action={"type": "string", "enum": ["list", "output", "stop"]}, id=_STR)),
    "todo": ("Replace the todo list. Send the whole list each time.",
             _obj(("items",), items={"type": "array", "items": _TODO_ITEM})),
    "task": ("Run a subagent on a fresh conversation and return its answer.", _AGENT_CALL),
    "tasks": ("Run up to four read-only subagents at the same time and return each answer.",
              _obj(("tasks",), tasks={"type": "array", "items": _AGENT_CALL})),
    "remember": ("Save one short fact about this project for later sessions.",
                 _obj(("note",), note=_STR)),
    "skill": ("Load the full text of a skill by name.", _obj(("name",), name=_STR)),
    "web_fetch": ("Read one web page as text.", _obj(("url",), url=_STR)),
    "web_search": ("Search the web and return titles, URLs and snippets.",
                   _obj(("query",), query=_STR)),
}

# A tool that needs something the session may not have. Offered only with it.
_NEEDS = {"task": "task_runner", "tasks": "task_runner", "remember": "memory_path",
          "skill": "skills", "run_background": "jobs", "processes": "jobs"}


def _spec(name: str, description: str, parameters: dict) -> dict:
    return {"name": name, "description": description, "parameters": parameters}


def for_executor(executor) -> list:
    """The tools this executor can serve, as [{name, description, parameters}].

    A subagent's tool list narrows it. External (MCP) tools follow the
    built-ins, with the input schema their server declared when it gave one.
    """
    allowed = getattr(executor, "allowed_tools", None)
    out = []
    for name, (description, parameters) in BUILTIN.items():
        need = _NEEDS.get(name)
        if need and not getattr(executor, need, None):
            continue
        if allowed is None or name in allowed:
            out.append(_spec(name, description, parameters))
    for name, entry in sorted((getattr(executor, "external", None) or {}).items()):
        if name in BUILTIN or not NAME.match(name) or not (allowed is None or name in allowed):
            continue
        schema = entry.get("schema") if isinstance(entry, dict) else None
        if not (isinstance(schema, dict) and schema.get("type") == "object"):
            schema = OPEN
        description = (entry.get("description") or "") if isinstance(entry, dict) else ""
        out.append(_spec(name, description[:1024] or f"External tool {name}.", schema))
    return out
