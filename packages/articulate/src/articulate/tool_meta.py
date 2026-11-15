"""Shared titles and MCP hints for the tools and their local mode.

Local mode returns host plans or deterministic edits. The default mode also
offers optional model backends; its editor hints reflect that wider access.
"""
import os

TOOLS_VAR = "ARTICULATE_MCP_TOOLS"
EDITORS = frozenset(("judge", "fix", "polish"))
TITLES = {
    "check": "Check prose for named patterns",
    "score": "Score prose patterns",
    "judge": "Assess prose with an optional hosted model",
    "fix": "Suggest a rewrite with an optional hosted model",
    "polish": "Polish prose with an optional hosted model",
    "edit_plan": "Prepare a local host edit plan",
    "edit_submit": "Check a local host rewrite",
    "corpus_check": "Review a series of documents together",
    "title_workshop": "Group a series' titles by formula",
    "interview": "Questions only the author can answer",
    "restructure_plan": "Propose moving limit and source lines",
    "voice_compare": "Compare a draft to your voice profile",
    "voice_apply_plan": "Plan an edit toward your own voice",
    "house_brief": "The house voice brief",
    "house_transform": "Apply the house voice to model output",
    "dialogue_check": "Check dialogue and character voices",
    "articulate.status": "Articulate server status",
    "articulate.doctor": "Articulate readiness check",
}
LOCAL_TITLES = {"judge": "Prepare a local assessment", "fix": "Prepare a local rewrite",
                "polish": "Prepare a local polish"}


def tool_set(environ=None):
    env = os.environ if environ is None else environ
    return "all" if env.get(TOOLS_VAR, "").strip().lower() in ("", "all") else "local"


def local_only_switch(environ=None):
    """ARTICULATE_LOCAL_ONLY as a boolean, read the same way backends.local_only reads it."""
    env = os.environ if environ is None else environ
    return env.get("ARTICULATE_LOCAL_ONLY", "").strip().lower() not in ("", "0", "false", "no", "off")


def offline(environ=None):
    env = os.environ if environ is None else environ
    switch = env.get("ARTICULATE_LOCAL_ONLY", "").strip().lower()
    return tool_set(env) == "local" or switch not in ("", "0", "false", "no", "off")


def annotations(name, environ=None):
    network = name in EDITORS and not offline(environ)
    title = LOCAL_TITLES.get(name, TITLES[name]) if offline(environ) else TITLES[name]
    return {"title": title, "readOnlyHint": not network, "destructiveHint": False,
            "idempotentHint": not network, "openWorldHint": network}


def fastmcp_options(name):
    hints = annotations(name)
    return {"title": hints["title"], "annotations": hints}


def is_listed(name, environ=None):
    # Every editor has an offline path, enforced by the shared MCP dispatcher.
    return name in TITLES
