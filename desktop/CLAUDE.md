# flywheel-desktop

Native Flutter desktop client for the Flywheel gateway (127.0.0.1:8799).
The engine (github.com/HarperZ9/flywheel, dev source in the local-model
checkout) owns the loop, receipts, lanes, and routing; this app renders them
and never reimplements them.

## Rules

- Design and voice come from the ecosystem canon of record
  (telos-v2/project-docs/DESIGN-VOICE-CANON.md) and the engine's own shell
  (local-model site/index.html). Tokens live in lib/theme/tokens.dart —
  never hardcode a color in a view. Two typefaces only. Color is verdict-only.
- Credentials: presence only, never values. The app never collects keys.
- Honest nulls stay visible. A view that cannot show DRIFT is not shipped.
- Every gateway-facing model parses defensively (missing fields degrade,
  never crash).
- Gates before commit: `flutter analyze` clean, `flutter test` green,
  files under 300 lines.

## Layout

- lib/theme — tokens + ThemeData builders
- lib/widgets — the shared grammar (fw.dart), aperture mark, side rail
- lib/views — one file per destination
- lib/client + lib/models — typed gateway API
- lib/services — settings persistence, engine child-process launcher
