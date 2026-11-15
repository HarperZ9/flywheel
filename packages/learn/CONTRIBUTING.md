# Contributing

This repository is part of the Project Telos public surface. Keep changes small, tested, and easy
for public users and developers to verify.

Before sending a change:

- Read `README.md` and `AGENTS.md`.
- Write the failing test first, confirm it fails, implement minimally, confirm it passes.
- Run the narrowest test slice that covers the change, then the full suite (`node --test`) to
  confirm no regressions.
- Run `node src/cli.mjs doctor` and confirm it reports `MATCH`.
- If the change touches or could be misread as touching the integrity line (see `AGENTS.md`), add
  a falsifiable test proving graded work is still never produced, hinted, or auto-filled, and wire
  the check into `doctor.mjs`.
- Keep examples, package metadata, and public claims in `README.md` aligned with current behavior.
- Do not add a dependency. Do not commit secrets, `.env` files, or generated caches.
