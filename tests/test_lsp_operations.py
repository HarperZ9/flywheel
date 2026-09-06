"""What each operation asks for, and what it must not send along with it.

A wrong parameter shape does not read as a wrong parameter shape. A server that
validates strictly answers InvalidParams, which surfaces as the feature not
working; a server that validates loosely answers about a position it guessed at.
Both look like an unsupported operation from the caller's side, so the shapes are
pinned here rather than discovered against a real server.
"""
import pytest

from harness.lsp_capabilities import PROVIDERS
from harness.lsp_operations import (OPERATIONS, UnknownOperation, method_of,
                                    params_for, shape_of)

URI = "file:///w/a.py"


def test_every_operation_names_a_method_in_a_namespace_servers_use():
    for name, (method, _) in OPERATIONS.items():
        assert method.startswith(("textDocument/", "workspace/")), name


def test_every_operation_is_one_this_client_can_check_the_server_for():
    # An operation whose availability cannot be read off the initialize result
    # would be sent hopefully, and a server that does not answer it would be
    # indistinguishable from one that answered nothing useful.
    assert {method for method, _ in OPERATIONS.values()} == set(PROVIDERS)


def test_a_name_this_client_does_not_make_says_so_and_lists_what_it_does():
    with pytest.raises(UnknownOperation, match="definition"):
        method_of("goto_definition")
    with pytest.raises(UnknownOperation):
        shape_of("")


def test_a_position_request_carries_the_document_and_the_position_only():
    params = params_for("definition", URI, line=3, character=7)
    assert params == {"textDocument": {"uri": URI},
                      "position": {"line": 3, "character": 7}}


def test_selection_range_carries_a_list_of_positions_not_one():
    # The singular field would earn an invalid-params refusal that reads like
    # the server not supporting the feature.
    params = params_for("selection_range", URI, line=1, character=2)
    assert "position" not in params
    assert params["positions"] == [{"line": 1, "character": 2}]


def test_references_asks_whether_the_declaration_counts():
    assert params_for("references", URI)["context"] == \
        {"includeDeclaration": True}
    assert params_for("references", URI, include_declaration=False)[
        "context"] == {"includeDeclaration": False}


def test_rename_carries_the_new_name_and_the_position_it_applies_at():
    params = params_for("rename", URI, line=5, character=1, new_name="b")
    assert params["newName"] == "b"
    assert params["position"] == {"line": 5, "character": 1}


def test_a_whole_document_request_sends_no_position_at_all():
    for name in ("symbols", "folding", "links", "code_lens", "semantic_tokens",
                 "diagnostic"):
        assert params_for(name, URI, line=9, character=9) == \
            {"textDocument": {"uri": URI}}, name


def test_formatting_carries_options_and_no_range():
    params = params_for("format", URI, tab_size=2, insert_spaces=False)
    assert params["options"] == {"tabSize": 2, "insertSpaces": False}
    assert "range" not in params


def test_range_formatting_carries_both_the_range_and_the_options():
    params = params_for("format_range", URI, line=1, character=0, end_line=4,
                        end_character=2)
    assert params["range"] == {"start": {"line": 1, "character": 0},
                               "end": {"line": 4, "character": 2}}
    assert params["options"]["tabSize"] == 4


def test_a_range_with_no_end_is_the_caret_and_not_the_rest_of_the_file():
    span = params_for("inlay_hints", URI, line=6, character=3)["range"]
    assert span["start"] == span["end"] == {"line": 6, "character": 3}


def test_a_code_action_carries_the_diagnostics_it_is_being_asked_about():
    given = [{"message": "unused import"}]
    params = params_for("code_action", URI, diagnostics=given)
    assert params["context"] == {"diagnostics": given}
    # Copied, so a caller mutating its list afterwards cannot change what was
    # recorded as having been sent.
    given.append({"message": "later"})
    assert len(params["context"]["diagnostics"]) == 1


def test_a_workspace_query_names_no_document():
    params = params_for("workspace_symbols", URI, query="Lsp")
    assert params == {"query": "Lsp"}


def test_executing_a_command_carries_the_command_and_its_arguments():
    assert params_for("execute_command", URI, command="ruff.fix",
                      arguments=[URI]) == {"command": "ruff.fix",
                                           "arguments": [URI]}
    assert params_for("execute_command", URI, command="x")["arguments"] == []


def test_no_operation_sends_a_field_its_method_does_not_define():
    allowed = {"textDocument", "position", "positions", "range", "context",
               "options", "newName", "query", "command", "arguments"}
    for name in OPERATIONS:
        assert set(params_for(name, URI)) <= allowed, name
