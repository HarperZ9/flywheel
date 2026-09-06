"""What this client promises, and how the server's answer is read back."""
import pytest

from harness.lsp_capabilities import (PROVIDERS, SYNC_FULL, SYNC_INCREMENTAL,
                                      SYNC_NONE, client_capabilities,
                                      initialize_params, negotiate_encoding,
                                      server_summary, supports, sync_kind,
                                      wants_open_close)
from harness.lsp_positions import ENCODINGS, UTF8, UTF16, UTF32


def answer(capabilities: dict, info: dict | None = None) -> dict:
    result = {"capabilities": capabilities}
    if info is not None:
        result["serverInfo"] = info
    return result


def test_the_client_offers_every_encoding_it_can_actually_convert():
    offered = client_capabilities()["general"]["positionEncodings"]
    assert set(offered) == set(ENCODINGS)
    assert offered[-1] == UTF16  # the fallback goes last, being least specific


def test_an_encoding_this_client_cannot_convert_is_never_offered():
    with pytest.raises(ValueError):
        client_capabilities(("utf-7",))


def test_dynamic_registration_is_declined_wherever_it_is_mentioned():
    # A capability that can appear mid-session can also disappear, which would
    # make an operation's availability change underneath a recorded answer.
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "dynamicRegistration":
                    found.append(value)
                walk(value)

    walk(client_capabilities())
    assert found and not any(found)


def test_initialize_params_carry_the_fields_a_server_reads_first():
    params = initialize_params("file:///w", process_id=42,
                               client_name="flywheel", client_version="0.3.0")
    assert params["processId"] == 42
    assert params["clientInfo"] == {"name": "flywheel", "version": "0.3.0"}
    assert params["rootUri"] == "file:///w"
    assert params["workspaceFolders"] == [{"uri": "file:///w", "name": "root"}]
    assert params["trace"] == "off"


def test_a_client_with_no_root_says_so_in_both_places():
    params = initialize_params(None, process_id=None, client_name="f",
                               client_version="0")
    assert params["rootUri"] is None
    assert params["workspaceFolders"] is None


def test_initialization_options_are_sent_only_when_there_are_some():
    plain = initialize_params(None, process_id=1, client_name="f",
                              client_version="0")
    assert "initializationOptions" not in plain
    with_options = initialize_params(None, process_id=1, client_name="f",
                                     client_version="0",
                                     initialization_options={"settings": {}})
    assert with_options["initializationOptions"] == {"settings": {}}


def test_a_server_that_names_no_encoding_means_utf_16():
    assert negotiate_encoding(answer({})) == UTF16
    assert negotiate_encoding({}) == UTF16


def test_a_server_choosing_an_offered_encoding_is_taken_at_its_word():
    assert negotiate_encoding(answer({"positionEncoding": UTF8})) == UTF8
    assert negotiate_encoding(answer({"positionEncoding": UTF32})) == UTF32


def test_a_server_choosing_an_encoding_nobody_offered_is_refused():
    # Accommodating it would mean converting positions with the wrong rule and
    # reporting success while reading the wrong span of every file.
    with pytest.raises(ValueError, match="not offered"):
        negotiate_encoding(answer({"positionEncoding": UTF8}), offered=(UTF16,))
    with pytest.raises(ValueError):
        negotiate_encoding(answer({"positionEncoding": "utf-7"}))


def test_a_provider_that_is_false_or_null_or_absent_means_no():
    assert not supports(answer({"hoverProvider": False}),
                        "textDocument/hover")
    assert not supports(answer({"hoverProvider": None}), "textDocument/hover")
    assert not supports(answer({}), "textDocument/hover")


def test_an_empty_options_object_still_means_yes():
    # The trap a truthiness check walks into: {} is falsy in Python and is a
    # legal way for a server to say it takes the request with nothing to set.
    assert supports(answer({"renameProvider": {}}), "textDocument/rename")
    assert supports(answer({"renameProvider": True}), "textDocument/rename")
    assert supports(answer({"codeActionProvider": {"codeActionKinds": []}}),
                    "textDocument/codeAction")


def test_a_method_this_client_does_not_ask_for_is_never_reported_supported():
    assert not supports(answer({"colorProvider": True}),
                        "textDocument/documentColor")


def test_every_method_in_the_map_names_a_provider_field():
    assert all(field.endswith("Provider") for field in PROVIDERS.values())
    assert len(set(PROVIDERS.values())) == len(PROVIDERS)


def test_the_sync_field_is_read_in_both_the_shapes_servers_send_it():
    assert sync_kind(answer({"textDocumentSync": SYNC_FULL})) == SYNC_FULL
    assert sync_kind(answer({"textDocumentSync": {
        "openClose": True, "change": SYNC_INCREMENTAL}})) == SYNC_INCREMENTAL


def test_a_server_that_says_nothing_about_sync_is_sent_nothing():
    assert sync_kind(answer({})) == SYNC_NONE
    assert sync_kind(answer({"textDocumentSync": {"openClose": True}})) == \
        SYNC_NONE
    assert not wants_open_close(answer({}))


def test_a_sync_value_outside_the_three_kinds_is_treated_as_none():
    assert sync_kind(answer({"textDocumentSync": 9})) == SYNC_NONE
    assert sync_kind(answer({"textDocumentSync": "full"})) == SYNC_NONE
    assert sync_kind(answer({"textDocumentSync": {"change": "full"}})) == \
        SYNC_NONE


def test_open_close_is_read_from_the_object_and_implied_by_the_number():
    assert wants_open_close(answer({"textDocumentSync": SYNC_FULL}))
    assert not wants_open_close(answer({"textDocumentSync": SYNC_NONE}))
    assert wants_open_close(answer({"textDocumentSync": {"openClose": True}}))
    assert not wants_open_close(answer({"textDocumentSync": {
        "openClose": False, "change": SYNC_FULL}}))


def test_the_summary_lists_what_the_server_answers_and_what_it_calls_itself():
    result = answer({"positionEncoding": UTF8,
                     "textDocumentSync": {"openClose": True, "change": 2},
                     "hoverProvider": True,
                     "definitionProvider": {},
                     "renameProvider": False},
                    {"name": "ruff", "version": "0.15.21"})
    assert server_summary(result) == {
        "name": "ruff", "version": "0.15.21",
        "position_encoding": UTF8, "sync_kind": SYNC_INCREMENTAL,
        "open_close": True,
        "methods": ["textDocument/definition", "textDocument/hover"]}


def test_a_server_that_says_nothing_summarizes_as_answering_nothing():
    assert server_summary({}) == {
        "name": "", "version": "", "position_encoding": UTF16,
        "sync_kind": SYNC_NONE, "open_close": False, "methods": []}
