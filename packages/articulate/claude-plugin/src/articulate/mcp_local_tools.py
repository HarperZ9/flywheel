"""FastMCP registration for the series, personal-voice, house-voice and dialogue tools.

Each wrapper declares its arguments for FastMCP's schema and passes them to the
same handler the stdio server uses, so both servers behave the same.
"""
from typing import List, Optional

from . import dialogue_tools, house_tools, voice_tools
from .tool_meta import fastmcp_options
from .tool_text import description


def _opts(name):
    return dict(name=name, description=description(name), **fastmcp_options(name))


def _given(**arguments):
    return {k: v for k, v in arguments.items() if v is not None}


def register(mcp):
    @mcp.tool(**_opts("corpus_check"))
    def corpus_check(documents: List[dict], keep: Optional[List[str]] = None,
                     genre: str = "essay", single: bool = False) -> dict:
        return voice_tools.handle("corpus_check", _given(documents=documents, keep=keep,
                                                         genre=genre, single=single))

    @mcp.tool(**_opts("title_workshop"))
    def title_workshop(titles: List[str], answers: Optional[List[str]] = None) -> dict:
        return voice_tools.handle("title_workshop", _given(titles=titles, answers=answers))

    @mcp.tool(**_opts("interview"))
    def interview(text: str, voice_name: Optional[str] = None) -> dict:
        return voice_tools.handle("interview", _given(text=text, voice_name=voice_name))

    @mcp.tool(**_opts("restructure_plan"))
    def restructure_plan(text: str, anchors: str = "footnote") -> dict:
        return voice_tools.handle("restructure_plan", _given(text=text, anchors=anchors))

    @mcp.tool(**_opts("voice_compare"))
    def voice_compare(text: str, voice_name: str) -> dict:
        return voice_tools.handle("voice_compare", _given(text=text, voice_name=voice_name))

    @mcp.tool(**_opts("voice_apply_plan"))
    def voice_apply_plan(text: str, voice_name: str, authored_by_user: bool,
                         author_text: Optional[str] = None) -> dict:
        return voice_tools.handle("voice_apply_plan", _given(
            text=text, voice_name=voice_name, authored_by_user=authored_by_user,
            author_text=author_text))

    @mcp.tool(**_opts("house_brief"))
    def house_brief(settings: Optional[dict] = None) -> dict:
        return house_tools.handle("house_brief", _given(settings=settings))

    @mcp.tool(**_opts("house_transform"))
    def house_transform(text: str, settings: Optional[dict] = None, house: bool = True) -> dict:
        return house_tools.handle("house_transform", _given(text=text, settings=settings,
                                                            house=house))

    @mcp.tool(**_opts("dialogue_check"))
    def dialogue_check(text: str, format: str = "auto", voices: Optional[List[dict]] = None,
                       theme_words: Optional[List[str]] = None, min_lines: int = 20,
                       worst: int = 30) -> dict:
        return dialogue_tools.handle("dialogue_check", _given(
            text=text, format=format, voices=voices, theme_words=theme_words,
            min_lines=min_lines, worst=worst))
