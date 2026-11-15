# AGENTS.md -- Agent Hook Pack

## Project Boundary

Agent Hook Pack publishes public-safe git and agent hook templates for release
hygiene. It focuses on local checks for secrets, branch guardrails, environment
template sync, lint hooks, and hook inventory audits. It does not include private
policy layers, private operator runbooks, or hidden automation.

## Public Delivery Rules

- Keep `README.md`, `USAGE.md`, `CHANGELOG.md`, `RELEASE.md`,
  `CONTRIBUTING.md`, `AUTHORS.md`, `LICENSE`, `.github/FUNDING.yml`,
  workflows, packaged hooks, examples, and package metadata aligned.
- Do not commit `.env` files, real secrets, private policy files, generated
  release artifacts, local caches, or private corpus material.
- Test fixtures may use credential-shaped examples only when they are assembled
  at runtime or clearly synthetic and incomplete.
- Keep hook behavior explicit and inspectable; no hidden network calls or
  background mutation.

## Developer Verification

```powershell
python -m pip install -e ".[test]"
python -m pytest
python -m build
```

Before publishing release artifacts, also run `python -m twine check dist/*`
after intentionally creating `dist/`.
