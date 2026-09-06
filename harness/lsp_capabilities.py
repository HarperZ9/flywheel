"""lsp_capabilities.py -- what this client claims, and what the server answered.

Capabilities are a promise in both directions, and the cost of overclaiming is
paid by the other side. A client that advertises a feature it does not implement
makes the server do work whose result gets dropped, and in the pull-diagnostics
and progress cases it makes the server wait on a reply that never comes. So what
is declared here is what the client actually does, and the shape of that list is
deliberately small.

Reading the server's answer has its own trap. A provider field is
`boolean | Options | null`, so `if result["capabilities"].get(field)` is right for
a boolean and wrong for an options object that happens to be empty, which is
legal and means yes. And `textDocumentSync` is either a number or an object,
depending on the server's age. Both shapes are read here, once, so no caller has
to remember which servers send which.
"""
from __future__ import annotations

from .lsp_positions import DEFAULT_ENCODING, ENCODINGS, check_encoding

#: How a server wants document changes delivered.
SYNC_NONE = 0
SYNC_FULL = 1
SYNC_INCREMENTAL = 2

#: The request each server capability gates. A method that is not in this map is
#: one this client does not ask for, which is why the map is short: it lists what
#: the client can do, not everything the specification defines.
PROVIDERS = {
    "textDocument/definition": "definitionProvider",
    "textDocument/declaration": "declarationProvider",
    "textDocument/typeDefinition": "typeDefinitionProvider",
    "textDocument/implementation": "implementationProvider",
    "textDocument/references": "referencesProvider",
    "textDocument/hover": "hoverProvider",
    "textDocument/documentSymbol": "documentSymbolProvider",
    "textDocument/documentHighlight": "documentHighlightProvider",
    "textDocument/diagnostic": "diagnosticProvider",
    "textDocument/codeAction": "codeActionProvider",
    "textDocument/formatting": "documentFormattingProvider",
    "textDocument/rangeFormatting": "documentRangeFormattingProvider",
    "textDocument/rename": "renameProvider",
    "textDocument/completion": "completionProvider",
    "textDocument/signatureHelp": "signatureHelpProvider",
    "textDocument/foldingRange": "foldingRangeProvider",
    "textDocument/selectionRange": "selectionRangeProvider",
    "textDocument/inlayHint": "inlayHintProvider",
    "textDocument/codeLens": "codeLensProvider",
    "textDocument/documentLink": "documentLinkProvider",
    "textDocument/semanticTokens/full": "semanticTokensProvider",
    "textDocument/prepareCallHierarchy": "callHierarchyProvider",
    "textDocument/prepareTypeHierarchy": "typeHierarchyProvider",
    "workspace/symbol": "workspaceSymbolProvider",
    "workspace/executeCommand": "executeCommandProvider",
}

__all__ = ["PROVIDERS", "SYNC_FULL", "SYNC_INCREMENTAL", "SYNC_NONE",
           "client_capabilities", "initialize_params", "negotiate_encoding",
           "server_summary", "supports", "sync_kind", "wants_open_close"]


def client_capabilities(offered: tuple[str, ...] = ENCODINGS) -> dict:
    """What this client can actually be asked to do.

    Dynamic registration is declined everywhere. A server that can register a
    capability mid-session can also unregister it, and an operation whose
    availability changes under the answer would make a record of that answer
    harder to read rather than easier.
    """
    for encoding in offered:
        check_encoding(encoding)
    return {
        "general": {"positionEncodings": list(offered)},
        "workspace": {
            "workspaceFolders": True,
            "configuration": True,
            "applyEdit": False,
            "didChangeConfiguration": {"dynamicRegistration": False},
            "symbol": {"dynamicRegistration": False},
        },
        "textDocument": {
            "synchronization": {"dynamicRegistration": False,
                                "willSave": False, "willSaveWaitUntil": False,
                                "didSave": False},
            "publishDiagnostics": {"relatedInformation": True,
                                   "versionSupport": True,
                                   "codeDescriptionSupport": True,
                                   "dataSupport": True,
                                   "tagSupport": {"valueSet": [1, 2]}},
            "diagnostic": {"dynamicRegistration": False,
                           "relatedDocumentSupport": False},
            "definition": {"dynamicRegistration": False, "linkSupport": True},
            "declaration": {"dynamicRegistration": False, "linkSupport": True},
            "typeDefinition": {"dynamicRegistration": False,
                               "linkSupport": True},
            "implementation": {"dynamicRegistration": False,
                               "linkSupport": True},
            "references": {"dynamicRegistration": False},
            "documentHighlight": {"dynamicRegistration": False},
            "hover": {"dynamicRegistration": False,
                      "contentFormat": ["plaintext", "markdown"]},
            "documentSymbol": {"dynamicRegistration": False,
                               "hierarchicalDocumentSymbolSupport": True},
            "formatting": {"dynamicRegistration": False},
            "rangeFormatting": {"dynamicRegistration": False},
        },
        "window": {"workDoneProgress": True, "showMessage": {}},
    }


def initialize_params(root_uri: str | None, *, process_id: int | None,
                      client_name: str, client_version: str,
                      offered: tuple[str, ...] = ENCODINGS,
                      initialization_options: dict | None = None,
                      trace: str = "off") -> dict:
    """The InitializeParams this client sends, in the order the spec lists them.

    processId is what lets a server outlive nothing: it exits when that process
    goes away. Passing null is legal and means the server has no parent to
    watch, which leaves a stranded process behind if this client is killed.
    """
    params = {
        "processId": process_id,
        "clientInfo": {"name": client_name, "version": client_version},
        "rootUri": root_uri,
        "capabilities": client_capabilities(offered),
        "trace": trace,
    }
    if initialization_options is not None:
        params["initializationOptions"] = initialization_options
    if root_uri is not None:
        params["workspaceFolders"] = [{"uri": root_uri, "name": "root"}]
    else:
        params["workspaceFolders"] = None
    return params


def negotiate_encoding(result: dict,
                       offered: tuple[str, ...] = ENCODINGS) -> str:
    """The encoding both sides will count positions in.

    Silence means utf-16, which is the only kind a server has to support. An
    answer naming something that was never offered is refused rather than
    accommodated: this client could not convert those positions correctly, and
    an operation that reads the wrong span of a file while reporting success is
    worse than one that does not run.
    """
    answered = (result or {}).get("capabilities", {}).get("positionEncoding")
    if answered is None:
        return DEFAULT_ENCODING
    if answered not in offered:
        raise ValueError(f"the server chose position encoding {answered!r}, "
                         f"which was not offered: {list(offered)}")
    return check_encoding(answered)


def supports(result: dict, method: str) -> bool:
    """Whether the server said it answers `method`.

    False and null and absent all mean no. Everything else means yes, including
    an empty options object, which is a legal way for a server to say it takes
    the request and has nothing to configure about it.
    """
    field = PROVIDERS.get(method)
    if field is None:
        return False
    value = (result or {}).get("capabilities", {}).get(field)
    return value is not False and value is not None


def _sync_options(result: dict) -> dict | int | None:
    return (result or {}).get("capabilities", {}).get("textDocumentSync")


def sync_kind(result: dict) -> int:
    """How the server wants changes delivered, from either shape of the field.

    A server saying nothing is treated as wanting none. That is the
    specification's default and it is also the safe reading: sending changes to
    a server that never asked for them makes it answer about text it was not
    tracking.
    """
    options = _sync_options(result)
    if isinstance(options, int):
        return options if options in (SYNC_NONE, SYNC_FULL,
                                      SYNC_INCREMENTAL) else SYNC_NONE
    if isinstance(options, dict):
        change = options.get("change", SYNC_NONE)
        return change if isinstance(change, int) else SYNC_NONE
    return SYNC_NONE


def wants_open_close(result: dict) -> bool:
    """Whether didOpen and didClose are worth sending at all."""
    options = _sync_options(result)
    if isinstance(options, dict):
        return bool(options.get("openClose", False))
    return isinstance(options, int) and options != SYNC_NONE


def server_summary(result: dict) -> dict:
    """What the server said about itself, in the shape a record carries."""
    result = result or {}
    info = result.get("serverInfo") or {}
    return {
        "name": info.get("name", ""),
        "version": info.get("version", ""),
        "position_encoding": negotiate_encoding(result),
        "sync_kind": sync_kind(result),
        "open_close": wants_open_close(result),
        "methods": sorted(method for method in PROVIDERS
                          if supports(result, method)),
    }
