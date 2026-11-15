# Release Checklist

## 0.2.0 Candidate

- [ ] Confirm `README.md`, `LICENSE`, `AUTHORS.md`, `CONTRIBUTING.md`, and
  `CHANGELOG.md` are present.
- [ ] Confirm `--telos-receipt` writes a bounded-run receipt without raw
  commands or raw stdout/stderr.
- [ ] Run `npm test`.
- [ ] Run `npm pack --dry-run`.
- [ ] Run `public-surface-sweeper . --summary`.
- [ ] Create a signed `v0.2.0` tag when signing is configured, or an
  annotated `v0.2.0` tag when it is not.
- [ ] Publish to npm only after account ownership, 2FA, provenance, and access
  settings are confirmed.

This repository does not auto-publish to a package registry.
