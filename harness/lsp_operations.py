"""lsp_operations.py -- the requests this client makes, and the params each takes.

One table instead of one function per request. The methods differ in their
parameter shape and in nothing else that matters here, and there are only nine
shapes across the whole set, so a table keeps the difference between
`textDocument/definition` and `textDocument/typeDefinition` where it actually
lives: in the method string.

The short names are the ones a caller types. They are stable, because they are
what harness/gateway.py's /api/lsp route and the desktop editor already send,
and a rename here would break an editor without breaking a test.

Positions here are already in the negotiated encoding. Converting them is
harness/lsp_positions.py's job and it happens before a request is built, so
nothing in this file has to know which encoding was agreed.
"""
from __future__ import annotations

#: shape -> what a caller has to supply beyond the document.
POSITION = "position"
POSITIONS = "positions"
REFERENCES = "references"
DOCUMENT = "document"
RANGE = "range"
CODE_ACTION = "code_action"
RENAME = "rename"
FORMATTING = "formatting"
RANGE_FORMATTING = "range_formatting"
QUERY = "query"
COMMAND = "command"

#: short name -> (LSP method, parameter shape). Everything this client can ask.
OPERATIONS: dict[str, tuple[str, str]] = {
    "definition": ("textDocument/definition", POSITION),
    "declaration": ("textDocument/declaration", POSITION),
    "type_definition": ("textDocument/typeDefinition", POSITION),
    "implementation": ("textDocument/implementation", POSITION),
    "references": ("textDocument/references", REFERENCES),
    "hover": ("textDocument/hover", POSITION),
    "highlight": ("textDocument/documentHighlight", POSITION),
    "completion": ("textDocument/completion", POSITION),
    "signature_help": ("textDocument/signatureHelp", POSITION),
    "call_hierarchy": ("textDocument/prepareCallHierarchy", POSITION),
    "type_hierarchy": ("textDocument/prepareTypeHierarchy", POSITION),
    "rename": ("textDocument/rename", RENAME),
    "symbols": ("textDocument/documentSymbol", DOCUMENT),
    "folding": ("textDocument/foldingRange", DOCUMENT),
    "links": ("textDocument/documentLink", DOCUMENT),
    "code_lens": ("textDocument/codeLens", DOCUMENT),
    "semantic_tokens": ("textDocument/semanticTokens/full", DOCUMENT),
    "diagnostic": ("textDocument/diagnostic", DOCUMENT),
    "format": ("textDocument/formatting", FORMATTING),
    "format_range": ("textDocument/rangeFormatting", RANGE_FORMATTING),
    "code_action": ("textDocument/codeAction", CODE_ACTION),
    "inlay_hints": ("textDocument/inlayHint", RANGE),
    # A list of positions, not one. The plural is the whole difference between
    # this request and every other position-shaped one, and sending the
    # singular field would earn an invalid-params refusal that reads like the
    # server not supporting the feature.
    "selection_range": ("textDocument/selectionRange", POSITIONS),
    "workspace_symbols": ("workspace/symbol", QUERY),
    "execute_command": ("workspace/executeCommand", COMMAND),
}

__all__ = ["OPERATIONS", "method_of", "params_for", "shape_of"]


class UnknownOperation(LookupError):
    """A name that is not one of this client's operations."""


def method_of(name: str) -> str:
    """The LSP method one short name stands for."""
    try:
        return OPERATIONS[name][0]
    except KeyError:
        raise UnknownOperation(
            f"{name!r} is not an operation this client makes; "
            f"try one of: {', '.join(sorted(OPERATIONS))}") from None


def shape_of(name: str) -> str:
    """Which parameters one short name needs."""
    method_of(name)
    return OPERATIONS[name][1]


def _position(line: int, character: int) -> dict:
    return {"line": int(line), "character": int(character)}


def _range(line: int, character: int, end_line: int | None,
           end_character: int | None) -> dict:
    """The span two positions name, with a caret standing for a missing end.

    An end that was not given is the start again, which is a range of width
    zero. That is the honest reading of "at this position" for a request whose
    shape is a range, and it is what an editor sends when nothing is selected.
    """
    start = _position(line, character)
    end = _position(line if end_line is None else end_line,
                    character if end_character is None else end_character)
    return {"start": start, "end": end}


def params_for(name: str, uri: str, *, line: int = 0, character: int = 0,
               end_line: int | None = None, end_character: int | None = None,
               new_name: str = "", query: str = "", command: str = "",
               arguments: list | None = None,
               diagnostics: list | None = None,
               include_declaration: bool = True,
               tab_size: int = 4, insert_spaces: bool = True) -> dict:
    """The params one operation carries, built from what the caller supplied.

    Everything past the document has a default, because most operations use
    almost none of it. What a shape does not read is not sent: a server that
    validates its params strictly refuses a message carrying a field its method
    does not define, and that refusal reads like an unsupported feature.
    """
    shape = shape_of(name)
    document = {"uri": uri}
    if shape == QUERY:
        return {"query": query}
    if shape == COMMAND:
        return {"command": command, "arguments": list(arguments or [])}
    if shape == POSITION:
        return {"textDocument": document,
                "position": _position(line, character)}
    if shape == POSITIONS:
        return {"textDocument": document,
                "positions": [_position(line, character)]}
    if shape == REFERENCES:
        return {"textDocument": document,
                "position": _position(line, character),
                "context": {"includeDeclaration": bool(include_declaration)}}
    if shape == RENAME:
        return {"textDocument": document,
                "position": _position(line, character), "newName": new_name}
    if shape == DOCUMENT:
        return {"textDocument": document}
    options = {"tabSize": int(tab_size), "insertSpaces": bool(insert_spaces)}
    if shape == FORMATTING:
        return {"textDocument": document, "options": options}
    span = _range(line, character, end_line, end_character)
    if shape == RANGE_FORMATTING:
        return {"textDocument": document, "range": span, "options": options}
    if shape == CODE_ACTION:
        return {"textDocument": document, "range": span,
                "context": {"diagnostics": list(diagnostics or [])}}
    return {"textDocument": document, "range": span}
