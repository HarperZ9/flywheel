Saved records written by older releases, kept so later releases prove they can
still read them (docs/VERSIONING.md, "Records stay checkable").

- code-session-1.6.0/: one `flywheel code -p` session saved by flywheel-verify
  1.6.0 from PyPI against a scripted model (one write_file call, then a reply).
  Only meta.json's `root` was edited afterwards, to a neutral path; `root` is
  not part of the hash chain or the conversation hash.
