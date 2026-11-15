"""Shared MCP tool bodies and the optional FastMCP transport.

Detection and host planning/submission are local. Auto editing borrows the
connected caller's model only when sampling was advertised, otherwise it
returns a host plan. Explicit hosted backends can send text off this machine.
"""
import asyncio
import json
from typing import List, Optional

from . import checkext as core
from .tool_meta import fastmcp_options, offline
from .tool_text import description


HITS_BUDGET = 30_000


def _within_budget(hits, budget=HITS_BUDGET):
    kept, used = [], 0
    for hit in hits:
        used += len(json.dumps(hit, separators=(",", ":"), ensure_ascii=False)) + 1
        if used > budget:
            break
        kept.append(hit)
    return kept


def _profile(name):
    """The named register or domain profile, or None when no name is given."""
    if name is None:
        return None
    if not isinstance(name, str):
        raise ValueError("profile must be a profile name")
    from . import domains, profiles
    try:
        return domains.load_profile(name)
    except profiles.ProfileError as exc:
        raise ValueError(str(exc)) from None


DEFAULT_RULES_NOTE = ("Default line rules only. The structure rules for a reply to a person "
                      "did not run, so clean here says nothing about them. Pass profile "
                      "\"chat\" to run them.")
TEXTURE_SCOPE = ("texture_score counts line rules only. Rule-pack findings are in hits and "
                 "pack_findings, and they count toward the gate.")


def rules_run(profile, prof):
    """Which rules a result came from, so a clean result under the default
    rules cannot be read as a clean result under a profile."""
    packs = sorted((prof or {}).get("rule_packs", ()))
    out = {"profile": profile or "default", "rule_packs": packs,
           "structure_rules": "structure" in packs}
    if not out["structure_rules"]:
        out["note"] = DEFAULT_RULES_NOTE if prof is None else (
            "Profile %s does not run the structure rules. Pass profile \"chat\" to check "
            "a reply to a person." % profile)
    return out


def _pack_fields(r):
    """Fields for a result that ran rule packs: their finding counts, and
    what the texture score leaves out."""
    if "pack_findings" not in r:
        return {}
    return {"pack_findings": r["pack_findings"], "texture_scope": TEXTURE_SCOPE}


def do_check(text, max_hits=None, profile=None):
    """Find named writing devices with span records. Runs on your machine.
    With `profile`, the check runs under that profile and its rule packs, and
    the result adds the profile name, the gate and the blocking count. Every
    result carries `rules_run`, which names the profile and rule packs used."""
    if max_hits is not None and (type(max_hits) is not int or not 0 <= max_hits <= 1000):
        raise ValueError("max_hits must be a whole number from 0 to 1000")
    prof = _profile(profile)
    r = core.check_text(text, profile=prof) if prof else core.check_text(text)
    hits = sorted(r["high"] + r["medium"], key=lambda h: h["start"])
    shown = hits if max_hits is None else _within_budget(hits[:max_hits])
    out = {
        "clean": r["clean"],
        "verdict": "clean" if r["clean"] else "flagged",
        "texture_score": r["texture_score"],
        "elevated": r["elevated"],
        "hits": shown,
        "advisory_count": len(r["low"]),
        "cadence": r["cadence"],
        "rules_run": rules_run(profile, prof),
    }
    if len(shown) < len(hits):
        out["hits_omitted"] = len(hits) - len(shown)
    if prof:
        out.update(profile=profile, gate=r["gate"], blocking_count=r["blocking_count"])
        out.update(_pack_fields(r))
    return out


def do_score(text, profile=None):
    """Graded device-density (texture) score and structural rates. Runs on your machine."""
    prof = _profile(profile)
    r = core.check_text(text, profile=prof) if prof else core.check_text(text)
    cad = r["cadence"]
    return {
        "rules_run": rules_run(profile, prof), **_pack_fields(r),
        **({"gate": r["gate"], "blocking_count": r["blocking_count"]} if prof else {}),
        "texture_score": r["texture_score"],
        "elevated": r["elevated"],
        "hard_hits": len(r["high"]) + len(r["medium"]),
        "advisories": len(r["low"]),
        "passive_rate": cad["passive_rate"],
        "adverb_rate": cad["adverb_rate"],
        "uniform_cadence": cad["uniform"],
        "words": cad["words"],
    }


def _edit(text, goal, **options):
    if offline():
        backend = options.get("backend")
        if backend not in (None, "auto", "host", "none"):
            return {"ok": False, "error": "%s backend %r is not available in local-only mode" % (goal, backend),
                    "note": "This local-only server allows host plans and backend none only."}
        from .host_edit import edit_plan, deterministic_edit
        bar, passes = options.get("bar", 4), options.get("passes", 3)
        if not 1 <= bar <= 5 or passes < 1:
            raise ValueError("bar must be 1-5 and passes must be positive")
        settings = {key: options[key] for key in ("mode", "profile", "is_html", "is_tex", "allow_change")
                    if key in options}
        result = (deterministic_edit if backend == "none" else edit_plan)(text, goal=goal, **settings)
        if goal == "polish":
            result.update(scores=None, quality_met=False)
        from .edit_notes import annotate_kept
        return annotate_kept(result, text, goal)
    try:
        from .editing import run_edit
    except ImportError:
        # The Claude plugin carries only the local tools and leaves editing out.
        return {"ok": False, "error": "%s needs a model backend, which this build does not include" % goal,
                "note": "Use the local tool set: host plans and backend none."}
    return run_edit(text, goal, context="mcp", **options)


def do_judge(text, backend=None, mode=None, profile=None, is_html=False,
             is_tex=False, **transport):
    return _edit(text, "judge", backend=backend, mode=mode, profile=profile,
                 is_html=is_html, is_tex=is_tex, **transport)


def _explained(text, result, explain):
    if explain:
        from .changes import attach
        attach(text, result)
    return result


def do_fix(text, is_html=False, backend=None, mode=None, profile=None,
           is_tex=False, allow_change=None, explain=False, **transport):
    if allow_change:
        transport["allow_change"] = allow_change
    return _explained(text, _edit(text, "fix", backend=backend, mode=mode, profile=profile,
                                  is_html=is_html, is_tex=is_tex, **transport), explain)


def do_polish(text, bar=4, passes=3, is_html=False, backend=None, mode=None,
              profile=None, is_tex=False, allow_change=None, explain=False, **transport):
    if allow_change:
        transport["allow_change"] = allow_change
    return _explained(text, _edit(text, "polish", bar=bar, passes=passes, backend=backend,
                                  mode=mode, profile=profile, is_html=is_html, is_tex=is_tex,
                                  **transport), explain)


def do_edit_plan(text, mode=None, profile=None, goal="fix", is_html=False, is_tex=False,
                 allow_change=None):
    from .host_edit import edit_plan
    return edit_plan(text, mode=mode, profile=profile, goal=goal,
                     is_html=is_html, is_tex=is_tex, allow_change=allow_change)


def do_edit_submit(text, rewrite, plan_id, scores=None, model=None, author_text=None,
                   explain=False):
    return _explained(text, _submit(text, rewrite, plan_id, scores, model, author_text), explain)


def _submit(text, rewrite, plan_id, scores, model, author_text):
    from .host_edit import edit_submit, plan_settings
    origin = "host-supplied" if author_text is not None else None
    if plan_settings(text, plan_id).get("voice_profile_sha256"):
        # A voice apply plan: check the bound profile is unchanged and report its counts.
        from .voice_apply import submit
        return submit(text, rewrite, plan_id, scores=scores, model=model,
                      author_text=author_text, author_text_origin=origin)
    return edit_submit(text, rewrite, plan_id, scores=scores, model=model,
                       author_text=author_text, author_text_origin=origin)


def _given(**options):
    """Only the options a caller set, so an unset one changes nothing downstream."""
    return {key: value for key, value in options.items() if value}


async def _fast_edit(ctx, text, goal, _explain=False, **options):
    """Bridge synchronous editing to the negotiated SDK session without an account."""
    from mcp.types import ClientCapabilities, SamplingCapability, SamplingMessage, TextContent
    loop = asyncio.get_running_loop()
    try:
        session = ctx.session
        advertised = session.check_client_capability(ClientCapabilities(sampling=SamplingCapability()))
    except (AttributeError, RuntimeError):
        session, advertised = None, False

    def sampling(instructions, passage, timeout):
        async def complete():
            result = await session.create_message(
                messages=[SamplingMessage(role="user", content=TextContent(type="text", text=passage))],
                system_prompt=instructions, max_tokens=4096, include_context="none")
            return result.model_dump(by_alias=True)
        future = asyncio.run_coroutine_threadsafe(complete(), loop)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            raise RuntimeError("sampling timed out") from None
        except Exception:
            raise RuntimeError("sampling request failed") from None

    result = await asyncio.to_thread(_edit, text, goal, sampling=sampling if advertised else None,
                                     sampling_advertised=advertised, **options)
    return _explained(text, result, _explain)


def build_server():
    from fastmcp import FastMCP, Context
    mcp = FastMCP("articulate")

    @mcp.tool(description=description("check"), **fastmcp_options("check"))
    def check(text: str, max_hits: int = 50, profile: Optional[str] = None) -> dict:
        """Find named writing devices and return findings with cadence stats. Runs on your machine."""
        return do_check(text, max_hits, profile)

    @mcp.tool(description=description("score"), **fastmcp_options("score"))
    def score(text: str, profile: Optional[str] = None) -> dict:
        """Return the device-density (texture) score and structural rates. Runs on your machine."""
        return do_score(text, profile)

    @mcp.tool(description=description("judge"), **fastmcp_options("judge"))
    async def judge(text: str, ctx: Context, backend: Optional[str] = None,
                    mode: Optional[str] = None, profile: Optional[str] = None,
                    is_html: bool = False, is_tex: bool = False) -> dict:
        """Assess prose using negotiated sampling or return a host edit plan; explicit hosted backends send text off the machine.
        When a plan is returned, follow its instructions and call edit_submit with the original text, assessment and plan_id."""
        return await _fast_edit(ctx, text, "judge", backend=backend, mode=mode,
                                profile=profile, is_html=is_html, is_tex=is_tex)

    @mcp.tool(description=description("fix"), **fastmcp_options("fix"))
    async def fix(text: str, ctx: Context, is_html: bool = False,
                  backend: Optional[str] = None, mode: Optional[str] = None,
                  profile: Optional[str] = None, is_tex: bool = False,
                  allow_change: Optional[List[str]] = None, explain: bool = False) -> dict:
        """Edit prose using negotiated sampling or return a host edit plan; explicit hosted backends send text off the machine.
        When a plan is returned, follow its instructions and call edit_submit with the original text, rewrite and plan_id."""
        return await _fast_edit(ctx, text, "fix", backend=backend, mode=mode,
                                profile=profile, is_html=is_html, is_tex=is_tex,
                                **_given(allow_change=allow_change), _explain=explain)

    @mcp.tool(description=description("polish"), **fastmcp_options("polish"))
    async def polish(text: str, ctx: Context, bar: int = 4, passes: int = 3,
                     is_html: bool = False, backend: Optional[str] = None,
                     mode: Optional[str] = None, profile: Optional[str] = None,
                     is_tex: bool = False, allow_change: Optional[List[str]] = None,
                     explain: bool = False) -> dict:
        """Polish prose with meaning and regression guards or return a host plan; explicit hosted backends send text off the machine.
        When a plan is returned, follow its instructions and call edit_submit with the original text, rewrite, plan_id and assessed scores."""
        return await _fast_edit(ctx, text, "polish", backend=backend, mode=mode,
                                profile=profile, is_html=is_html, is_tex=is_tex,
                                bar=bar, passes=passes, **_given(allow_change=allow_change),
                                _explain=explain)

    @mcp.tool(description=description("edit_plan"), **fastmcp_options("edit_plan"))
    def edit_plan(text: str, mode: Optional[str] = None, profile: Optional[str] = None,
                  goal: str = "fix", is_html: bool = False, is_tex: bool = False,
                  allow_change: Optional[List[str]] = None) -> dict:
        """Prepare local findings, protected spans and exact instructions for the calling model without a second account.
        Follow the instructions using masked_text and call edit_submit with the original text, rewrite or assessment, and plan_id."""
        return do_edit_plan(text, mode, profile, goal, is_html, is_tex, allow_change)

    @mcp.tool(description=description("edit_submit"), **fastmcp_options("edit_submit"))
    def edit_submit(text: str, rewrite: str, plan_id: str, scores: Optional[dict] = None,
                    model: Optional[str] = None, author_text: Optional[str] = None,
                    explain: bool = False) -> dict:
        """Submit the original text and a host rewrite or assessment using the plan_id from edit_plan.
        Articulate restores masks, guards protected spans, checks the result and returns accepted text with a host receipt."""
        return do_edit_submit(text, rewrite, plan_id, scores, model, author_text, explain)

    from .mcp_local_tools import register
    register(mcp)
    return mcp


if __name__ == "__main__":
    build_server().run()
