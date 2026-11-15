# Release Checklist

## 0.2.0 Published

- [ ] Confirm `README.md`, `LICENSE`, `AUTHORS.md`, `CONTRIBUTING.md`, and
  `CHANGELOG.md` are present.
- [ ] Confirm `--telos-envelope` writes `project-telos-context-envelope.json`
  without absolute paths or raw transcripts.
- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m build`.
- [ ] Run `python -m twine check dist/*`.
- [ ] Run `public-surface-sweeper . --summary`.
- [x] Published GitHub release `v0.2.0` from merge commit `c3532afb0c252e1e38828afdaf4544f71ce2e510`.
- [x] Uploaded checked release assets:
  - `context_curator_lite-0.2.0-py3-none-any.whl`: `e0323946afe9a075c4916759c70280987e57813d5fc6126cfdcbbfdeb6cf1556`
  - `context_curator_lite-0.2.0.tar.gz`: `50bd0fa1fbb7efd34880c9538650b40647aab3f9ceb622aae8dec0b45f5c8958`
- [ ] Publish to PyPI only after account ownership, 2FA, and trusted publishing
  configuration are confirmed.

This repository does not auto-publish to a package registry, and v0.2.0 is not on PyPI.
