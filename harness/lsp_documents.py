"""lsp_documents.py -- what the client says the files hold, and at which version.

A language server answers about the document it was told about, not about the
file on disk. Once a client sends didOpen, the server stops reading the file and
the client owns the content until didClose. Everything the server says after that
is an opinion about the text this store is holding.

That is why the version travels with the answer. An LSP request carries a
document identifier and not a version, so a reply that arrives after an edit is
about text nobody is looking at any more. The server has ContentModified (-32801)
for the cases it notices, and no way to signal the cases it does not. A client
that means to leave a recheckable record has to stamp the version itself, which
is what `stamp` is for.

URIs are the other quiet failure. A wrong file URI is not an error: the server
answers about a document it has never seen, and the answer is an empty list. On
Windows the drive letter and the separators are exactly where that goes wrong, so
the conversion lives here in one place and is tested in both directions.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from .lsp_positions import DEFAULT_ENCODING, offset_of, split_lines

__all__ = ["Document", "Documents", "UnknownDocument", "apply_change",
           "from_uri", "to_uri"]

#: The version a document carries the moment it is opened. LSP only requires
#: that the number increase, and starting at one leaves zero meaning "never
#: opened" rather than meaning something a server could also have sent.
FIRST_VERSION = 1


class UnknownDocument(LookupError):
    """A document was named that this client never opened, or already closed."""


def to_uri(path: str | Path) -> str:
    """The file URI for a path on disk, absolute, in the form servers accept."""
    return Path(path).resolve().as_uri()


def from_uri(uri: str) -> Path:
    """The path a file URI names. Raises for a URI that is not a file."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"a document path comes from a file URI, got {uri!r}")
    if parsed.netloc and parsed.netloc.lower() != "localhost":
        # \\\\server\\share becomes file://server/share and stays a UNC path.
        return Path(f"//{parsed.netloc}{unquote(parsed.path)}")
    return Path(url2pathname(parsed.path))


@dataclass(frozen=True)
class Document:
    """One open document: what the server was told, and when."""

    uri: str
    language_id: str
    version: int
    text: str

    def item(self) -> dict:
        """The TextDocumentItem shape didOpen carries."""
        return {"uri": self.uri, "languageId": self.language_id,
                "version": self.version, "text": self.text}

    def stamp(self) -> dict:
        """What an answer about this document should be recorded against."""
        return {"uri": self.uri, "version": self.version,
                "characters": len(self.text),
                "lines": len(split_lines(self.text))}


def apply_change(text: str, change: dict, encoding: str) -> str:
    """One TextDocumentContentChangeEvent applied to the text it describes.

    A change with no range replaces the whole document, which is what a client
    sends when it does not want to track ranges and what a server falls back to
    when it does not advertise incremental sync.
    """
    if "text" not in change:
        raise ValueError("a content change carries the text it inserts")
    span = change.get("range")
    if span is None:
        return change["text"]
    start = offset_of(text, span.get("start", {}), encoding)
    end = offset_of(text, span.get("end", {}), encoding)
    if end < start:
        raise ValueError("a content change range ends before it starts")
    return text[:start] + change["text"] + text[end:]


class Documents:
    """The open set, and the version each document is at.

    Not thread-safe on purpose. A document store that took a lock would invite a
    caller to edit from two threads, and two edits that interleave produce a
    version number that describes neither of them. The client owns the order.
    """

    def __init__(self, encoding: str = DEFAULT_ENCODING) -> None:
        self.encoding = encoding
        self._open: dict[str, Document] = {}

    def __contains__(self, uri: str) -> bool:
        return uri in self._open

    def __len__(self) -> int:
        return len(self._open)

    def uris(self) -> tuple[str, ...]:
        """Every document this client currently owns."""
        return tuple(self._open)

    def get(self, uri: str) -> Document:
        """The document, or say plainly that it was never opened."""
        try:
            return self._open[uri]
        except KeyError:
            raise UnknownDocument(f"{uri} is not open") from None

    def stamp(self, uri: str) -> dict:
        """What an answer about `uri` should be recorded against."""
        return self.get(uri).stamp()

    def is_current(self, uri: str, version: int) -> bool:
        """Whether an answer taken at `version` still describes this document."""
        return uri in self._open and self._open[uri].version == version

    def did_open(self, uri: str, language_id: str, text: str) -> dict:
        """Take ownership of a document. Returns the params didOpen carries."""
        if uri in self._open:
            raise ValueError(f"{uri} is already open")
        document = Document(uri, language_id, FIRST_VERSION, text)
        self._open[uri] = document
        return {"textDocument": document.item()}

    def open_path(self, path: str | Path, language_id: str) -> dict:
        """Read a file from disk and open it, in one step, as a client does."""
        location = Path(path)
        return self.did_open(to_uri(location), language_id,
                             location.read_text(encoding="utf-8"))

    def did_change(self, uri: str, changes: list[dict]) -> dict:
        """Apply changes in order and bump the version. Returns the params.

        In order matters: each change in the list describes the text as the ones
        before it left it, so applying them out of order silently corrupts the
        client's copy while the server's copy stays right.
        """
        document = self.get(uri)
        text = document.text
        for change in changes:
            text = apply_change(text, change, self.encoding)
        updated = replace(document, text=text, version=document.version + 1)
        self._open[uri] = updated
        return {"textDocument": {"uri": uri, "version": updated.version},
                "contentChanges": list(changes)}

    def replace_text(self, uri: str, text: str) -> dict:
        """Change the whole document, for a client not tracking ranges."""
        return self.did_change(uri, [{"text": text}])

    def did_close(self, uri: str) -> dict:
        """Hand the document back to the server's own view of the file."""
        self.get(uri)
        del self._open[uri]
        return {"textDocument": {"uri": uri}}

    def close_all(self) -> list[dict]:
        """Release every document, so shutdown leaves nothing half-owned."""
        return [self.did_close(uri) for uri in self.uris()]
