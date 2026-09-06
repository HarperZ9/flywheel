"""receipt_secrets.py -- whether a workdir file may travel inside a receipt.

oracle_inputs.py carries a task's fixture set into the receipt so a re-checker
can rebuild the oracle environment without being handed one. That put working
directory text into an artefact meant to be published, which makes "is this
file a credential" a question the capture path now has to answer before it
writes anything down.

Two rules, because they miss different things. A name rule catches `.env` and
`id_rsa` whatever they hold, including a six-character password no pattern will
match. A content rule catches a key pasted into a file named nothing in
particular. Both are cheap and neither covers the other.

Withheld whole, never masked. Masking a secret out of a fixture leaves a file
that still looks complete and now runs differently, and under the asymmetry in
grounding.py a fixture that is present but altered is worth less than one that
is absent: absence can only cost a confirmation, a quiet substitution is the
kind of thing that grants one. This is the argument the capture bounds already
make about truncating an oversized file.

The cost is a false withhold, and it is real. A fixture that legitimately
contains the word password followed by eight characters gets dropped, its task
loses fresh-environment reach, and the verdict degrades to UNVERIFIABLE. That
is the safe direction rather than a free one, which is why what got withheld is
recorded on the envelope instead of vanishing. A withheld entry discloses its
path and the type of thing found there, never the matched text, and a caller
who considers the path itself sensitive can switch capture off entirely with
`capture_oracle_inputs=False`.

Detection is delegated to harness.infra.credential_scanner rather than
duplicated. Its findings carry a fingerprint and a type; the secret text never
leaves the scan.
"""
from __future__ import annotations

from .infra.credential_scanner import scan_text

# Credential files by convention, whatever their contents turn out to be.
SECRET_NAMES = frozenset({
    ".env", ".envrc", ".netrc", "_netrc", ".npmrc", ".pypirc",
    ".git-credentials", ".htpasswd", ".pgpass", ".dev.vars",
    "credentials", "credentials.json", "secrets.json",
    "service-account.json", "wrangler.toml",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
})
# Key material by extension.
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".ppk")
# A path segment under which nothing is a fixture.
SECRET_DIRS = frozenset({".ssh", ".aws", ".gnupg", ".docker"})
# `.env.example` is a template the engineering standard requires a repo to
# commit, so treating every `.env.*` as a secret would withhold a file whose
# whole purpose is to be readable.
TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")

_UNDER_DIR = "sits under a credential directory"
_BY_NAME = "named like a credential file"
_BY_ENV = "named like an environment file"


def withhold_reason(rel: str, text: str = "") -> str | None:
    """Why this file must not travel in a receipt, or None to carry it.

    `rel` is a workdir-relative POSIX path and `text` its contents. The name is
    decided first: it is conclusive on its own and costs no scan, and it is the
    half that still works when the secret is too short to match a pattern.
    """
    parts = rel.split("/")
    name = parts[-1]
    if SECRET_DIRS.intersection(parts[:-1]):
        return _UNDER_DIR
    if name in SECRET_NAMES or name.endswith(SECRET_SUFFIXES):
        return _BY_NAME
    if name.startswith(".env.") and not name.endswith(TEMPLATE_SUFFIXES):
        return _BY_ENV
    found = scan_text(text or "", location=rel)
    return "contains a %s" % found[0].secret_type if found else None
