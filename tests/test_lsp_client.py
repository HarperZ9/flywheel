"""The client against a real subprocess, and the two things that fail silently.

Both silent failures are covered here on purpose. A position converted under the
wrong encoding names a real place in the file, so the server answers about the
wrong span and nothing raises: the highlight echo makes the number visible. An
answer that arrives after an edit describes text nobody is holding, and the only
signal is the version the client stamped itself.
"""
import sys
import time
from pathlib import Path

import pytest

from harness.lsp_client import (Answer, LspClient, NotInitialized,
                                UnsupportedOperation)
from harness.lsp_positions import UTF8, UTF16, UTF32

FAKE = [sys.executable, str(Path(__file__).parent / "fake_lsp_server.py")]

#: One line holding a character outside the basic plane, and the index of the
#: letter after it. Python counts that letter at 6, utf-16 at 7, utf-8 at 9.
ASTRAL = 'q = "\U0001f600b"\n'
AFTER_ASTRAL = 6


def wait_for(predicate, timeout=10.0):
    """Poll until a notification has arrived, or say which one never did."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError(f"nothing satisfied {predicate} within {timeout:g}s")


@pytest.fixture
def server(tmp_path):
    started = []

    def start(*flags):
        client = LspClient.start(FAKE + list(flags), root=tmp_path)
        started.append(client)
        client.initialize(client_name="flywheel", client_version="0.3.0")
        return client

    yield start
    for client in started:
        client.shutdown(timeout=5.0)
        client.close()


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_initialize_reads_back_what_the_server_said_it_is(server):
    client = server()
    assert client.summary()["name"] == "fake"
    assert client.summary()["version"] == "1"
    assert client.encoding == UTF16
    assert "textDocument/definition" in client.summary()["methods"]
    assert client.alive()


def test_a_server_naming_an_encoding_is_taken_at_its_word(server):
    assert server("--encoding", UTF8).encoding == UTF8
    assert server("--encoding", UTF32).encoding == UTF32


def test_a_request_before_initialize_is_refused_rather_than_sent(tmp_path):
    client = LspClient.start(FAKE, root=tmp_path)
    try:
        with pytest.raises(NotInitialized):
            client.ask("definition", "file:///w/a.py")
    finally:
        client.close()


def test_a_definition_comes_back_stamped_with_the_version_it_was_asked_at(
        server, tmp_path):
    client = server()
    uri = client.open(write(tmp_path, "a.py", "one\ntwo\nthree\n"), "python")
    answer = client.ask("definition", uri, line=0, character=0)
    assert isinstance(answer, Answer)
    assert answer.method == "textDocument/definition"
    assert answer.result[0]["range"]["start"]["line"] == 2
    assert answer.stamp["version"] == 1
    # Four, because the trailing newline opens a line the caret can sit on.
    assert answer.stamp["lines"] == 4
    assert answer.current is True
    assert answer.encoding == UTF16


def test_an_operation_the_server_never_advertised_is_refused_under_strict(
        server, tmp_path):
    client = server()
    uri = client.open(write(tmp_path, "a.py", "one\n"), "python")
    with pytest.raises(UnsupportedOperation, match="textDocument/rename"):
        client.ask("rename", uri, new_name="two", strict=True)
    # Without strict it goes out anyway, because a server answering a request it
    # did not advertise is common and the answer is still an answer.
    assert client.ask("rename", uri, new_name="two").result is None


def test_opening_a_file_gets_the_diagnostics_the_server_publishes(
        server, tmp_path):
    client = server()
    uri = client.open(write(tmp_path, "a.py", "broken thing\n"), "python")
    published = wait_for(lambda: client.diagnostics(uri).items)
    assert published[0]["message"] == "fake: broken symbol"
    assert client.diagnostics(uri).version == 1
    assert client.diagnostics(uri).current is True


def test_a_file_nobody_published_about_is_not_the_same_as_a_clean_one(server):
    client = server()
    nothing = client.diagnostics("file:///w/never.py")
    assert nothing.items == []
    assert nothing.version is None
    assert nothing.current is None


def test_changing_the_buffer_republishes_against_the_new_version(
        server, tmp_path):
    client = server()
    uri = client.open(write(tmp_path, "a.py", "broken thing\n"), "python")
    wait_for(lambda: client.diagnostics(uri).items)
    assert client.replace(uri, "fine thing\n") == 2
    wait_for(lambda: client.diagnostics(uri).version == 2)
    assert client.diagnostics(uri).items == []


def test_a_diagnostic_set_for_an_older_version_is_reported_as_stale(
        server, tmp_path):
    client = server()
    uri = client.open(write(tmp_path, "a.py", "one\n"), "python")
    client.replace(uri, "two\n")
    client.accept_diagnostics({"uri": uri, "version": 1, "diagnostics": [{}]})
    assert client.diagnostics(uri).current is False


def test_a_diagnostic_set_with_no_version_cannot_be_called_fresh(
        server, tmp_path):
    client = server()
    uri = client.open(write(tmp_path, "a.py", "one\n"), "python")
    client.accept_diagnostics({"uri": uri, "diagnostics": [{}]})
    # None, not True. The server did not say, and answering True here would be
    # inventing the one fact the field exists to carry.
    assert client.diagnostics(uri).current is None


def test_a_python_index_past_an_astral_character_converts_to_utf_16(
        server, tmp_path):
    client = server()
    uri = client.open(write(tmp_path, "a.py", ASTRAL), "python")
    echoed = client.ask_at("highlight", uri, 0, AFTER_ASTRAL)
    assert echoed.result[0]["range"]["start"]["character"] == 7
    assert echoed.params["position"]["character"] == 7


def test_the_same_index_converts_differently_once_utf_8_is_negotiated(
        server, tmp_path):
    # The false-success control. Both runs name the same letter, and a client
    # that ignored the negotiated encoding would send 7 to a server counting
    # bytes and get an answer about the middle of the emoji.
    client = server("--encoding", UTF8)
    uri = client.open(write(tmp_path, "a.py", ASTRAL), "python")
    echoed = client.ask_at("highlight", uri, 0, AFTER_ASTRAL)
    assert echoed.result[0]["range"]["start"]["character"] == 9


def test_the_client_answers_the_configuration_request_a_server_sends(server):
    client = server("--ask-configuration")
    message = wait_for(lambda: next(
        (m for m in client.messages if "configuration" in m["message"]), None))
    # One null per requested item, which is how a client says it has no settings
    # for that section. A bare null would be a different answer.
    assert "[null]" in message["message"]
    assert client.registrations == []


def test_closing_a_document_hands_it_back_and_forgets_the_version(
        server, tmp_path):
    client = server()
    uri = client.open(write(tmp_path, "a.py", "one\n"), "python")
    client.close_document(uri)
    assert uri not in client.documents
    with pytest.raises(LookupError):
        client.ask("definition", uri)


def test_syncing_opens_once_and_replaces_after(server, tmp_path):
    client = server()
    path = write(tmp_path, "a.py", "one\n")
    uri = client.sync(path, "one\n", "python")
    assert client.documents.get(uri).version == 1
    assert client.sync(path, "two\n", "python") == uri
    assert client.documents.get(uri).version == 2
    assert client.documents.get(uri).text == "two\n"


def test_shutdown_ends_the_process_rather_than_leaving_it_running(
        server, tmp_path):
    client = server()
    client.open(write(tmp_path, "a.py", "one\n"), "python")
    client.shutdown(timeout=5.0)
    client.close()
    assert not client.alive()
    assert len(client.documents) == 0


class Interleaving:
    """A connection that edits the document while the request is in flight.

    Written as a stub rather than raced against the real server, because the
    window this covers is a scheduling accident and a test that waits for one is
    a test that passes for the wrong reason on a slow machine.
    """

    def __init__(self) -> None:
        self.client = None
        self.handler = None
        self.notified: list[str] = []

    def call(self, method, params=None, timeout=None):
        if method == "initialize":
            return {"capabilities": {
                "textDocumentSync": {"openClose": True, "change": 1},
                "definitionProvider": True}}
        self.client.replace(params["textDocument"]["uri"], "edited\n")
        return []

    def notify(self, method, params=None):
        self.notified.append(method)

    def close(self, reason=None):
        pass


def test_an_answer_that_arrives_after_an_edit_is_marked_not_current(tmp_path):
    connection = Interleaving()
    client = LspClient(connection)
    connection.client = client
    client.initialize()
    uri = client.open(write(tmp_path, "a.py", "one\n"), "python")
    answer = client.ask("definition", uri)
    assert answer.stamp["version"] == 1
    assert client.documents.get(uri).version == 2
    assert answer.current is False


def test_closing_without_shutdown_ends_the_server_on_end_of_file(tmp_path):
    # Return code 0, not a kill. A stdio server whose stdin is closed reads
    # end-of-file and returns; one whose stdin stays open waits out the whole
    # grace period and is then killed, which is slow and looks identical from
    # the caller's side.
    client = LspClient.start(FAKE, root=tmp_path)
    client.initialize()
    client.close(grace=30.0)
    assert not client.alive()
    assert client.process.returncode == 0
