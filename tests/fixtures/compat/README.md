Saved records written by older releases, kept so later releases prove they can
still read them (docs/VERSIONING.md, "Records stay checkable").

- code-session-1.6.0/: one `flywheel code -p` session saved by flywheel-verify
  1.6.0 from PyPI against a scripted model (one write_file call, then a reply).
  Only meta.json's `root` was edited afterwards, to a neutral path; `root` is
  not part of the hash chain or the conversation hash.
- records-1.x/: one sealed record set from each 1.x minor, 1.0 to 1.9, written
  by that release from PyPI: the gate envelope, its report, and a receipt.
  Its own README has the wheel digests, the commands and the controls.
