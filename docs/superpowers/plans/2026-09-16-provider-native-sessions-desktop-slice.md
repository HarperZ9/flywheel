# Provider-native sessions desktop slice - 2026-09-16

Status: first desktop integration increment. This note records the bounded Dart slice only. It does not claim provider runtime readiness, account readiness, installed UI acceptance, provider generation, or release acceptance.

## Implemented scope

- Typed Dart request builders for `provider.session.turn`, `provider.session.resume`, and `provider.session.reconcile`.
- Desktop operation dispatch admission for `/api/provider-sessions/turn`, `/api/provider-sessions/resume`, and `/api/provider-sessions/reconcile`.
- Operation result parsing for provider-session terminal actions.
- Provider-session state folding from `progress.provider_session`, including stale operation-ref rejection and an explicit reconcile-required state for indeterminate writes.
- A standalone inspectable `ProviderSessionPane` showing provider/native IDs, phase, history status, side-effect status, and send/stop/resume/reconcile controls.

## Deliberate limits

- No provider launch, provider authentication read, provider generation, install, build, or full suite was run for this slice.
- The pane is not yet wired into `AgentView`; the current chat header only switches between text chat and workspace-agent mode, so route integration remains the next owner-coordinated UI step.
- Runtime provider approval requests are not yet an interactive UI queue. This slice can display folded provider state but does not authorize native provider tool decisions.
- Canon capture and source-context attachment APIs are not changed. The typed request can carry `attachment_refs`; UI selection and Canon turn capture remain separate work.
- Recovery persistence is not changed. `JourneySessionStore` still requires a later provider-session recovery mode or a separate recovery source.

## Verification run for this slice

- `C:/flutter/bin/flutter.bat test test/provider_session_operation_test.dart test/provider_session_client_test.dart test/provider_session_controller_test.dart test/provider_session_pane_test.dart`
- `C:/flutter/bin/flutter.bat analyze` on the touched Dart files and tests
- `python scripts/check_file_gate.py`
- `git diff --check`

## Next coherent step

Wire `ProviderSessionPane` into the chat/agent surface behind an explicit native-session mode, then add a fake-gateway widget test that proves a prepared provider turn uses the grant sheet and dispatches to `/api/provider-sessions/turn` without calling `/v1/chat/completions` or `/api/agent`.
