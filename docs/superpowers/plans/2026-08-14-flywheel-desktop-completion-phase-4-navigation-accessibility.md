# Flywheel Desktop Completion Phase 4 Navigation Accessibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve all 29 existing destinations plus Journey in five stable groups while adding route history, search, complete keyboard/semantic access, assistive display support, and typed recovery.

**Architecture:** Stable route IDs and typed locations replace labels and arbitrary payloads; a controller owns history while a retained-view cache preserves local selection and scroll. Shared accessible actions cover every remaining pointer surface, and a Recovery Center composes existing journals without becoming a thirty-first legacy destination or mutating server evidence implicitly.

**Tech Stack:** Flutter 3.44.6, Dart 3.6+, Phase 2/3 controllers and local stores, Flutter semantics/focus/actions APIs, Flutter test.

**Spec:** `docs/superpowers/specs/2026-08-13-flywheel-desktop-completion-design.md`

## Global Constraints

- No learned model on the accept path.
- No receipt, no accept; denominators and `does_not_prove` are mandatory.
- No later phase may become an implementation prerequisite for an earlier phase.
- Python containment is an independent capability gate and does not reorder these phases.
- Flutter must not derive evidence truth or treat receipt presence as verification.
- Write, exec, plugin, and network access default to denied; secrets use opaque credential handles and never enter Journey events.
- Telemetry is off by default.
- Missing containment must retain the accepted EXECUTION_CONTAINMENT_UNAVAILABLE null and must never fall back to ordinary execution or claim sandboxing.
- No provider, endpoint, model, or network dispatch from evidence routes
- New Python and Dart files stay at or below 300 physical lines.
- The verifier path keeps zero third-party runtime dependencies.
- Existing public paths, secrets, private artifacts, and historical receipts never enter fixtures.
- Each implementation task uses RED, GREEN, focused regression, gates, review, then a narrow commit.
- No public release is permitted before all six phases pass, even if it uses the non-executing profile.

---

## Per-task evidence envelope

For every numbered task, record `git rev-parse HEAD`, `git rev-parse HEAD^{tree}`, branch/worktree identity, and clean task-boundary status before RED. New production files stay at or below 300 physical lines, grandfathered over-limit files shrink, new/modified production functions stay at or below 60 lines, and test functions stay at or below 80 lines. Before handoff, record exact RED/GREEN/verification commands and exits, test and mutation denominators, touched-file SHA-256 values, measured file/function ceilings, limitations, `does_not_prove`, the task commit as rollback point, and receiving-owner acceptance. A missing field blocks the next task; reject with `git revert --no-edit HEAD` and rerun phase-to-date gates.

### Task P4-T1: Freeze the 30 stable routes and typed history

**Files:**
- Create: `desktop/lib/navigation/app_route.dart`
- Create: `desktop/lib/navigation/destination_catalog.dart`
- Create: `desktop/lib/navigation/navigation_controller.dart`
- Test: `desktop/test/navigation_catalog_test.dart`
- Test: `desktop/test/navigation_controller_test.dart`
- Test: `desktop/test/deep_link_test.dart`

**Interfaces:**
- Consumes: Phase 2 Journey home and 29 existing views; Phase 3 `UnsavedWorkGuard` and opaque refs.
- Produces: `DestinationId`, `DestinationSpec`, `AppLocation(routeId,journeyRef,selectionRef,viewState,scrollOffset)`, `parseDeepLink(Uri)`, and `NavigationController.go/back/forward`.

- [ ] **Write RED tests.** Require exactly 30 unique IDs and this exact catalog: Work `journey,plan,workflows,projects`; Chat `chat,compare,models,companion`; Code `code,eval,audit,lint`; Evidence `receipts,science,world,memory,governance,usage`; Advanced `studio,graph,feeds,discourse,academy,lessons,instruments,lanes,train,uplift,family,plugins`. Rename a label without changing identity, restore back/forward state, and reject deep links containing paths, hosts, unknown keys, or non-opaque refs.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/navigation_catalog_test.dart test/navigation_controller_test.dart test/deep_link_test.dart`; expect compile failure because typed navigation does not exist.
- [ ] **Implement minimal GREEN.** Route IDs are lowercase constants, deep links carry only allowlisted `jrn_|op_|rcpt_` public refs, history stores no widget/object/path, and `go` awaits `UnsavedWorkGuard` before committing a location.
- [ ] **Verify.** Run the RED command and `flutter analyze`; expect PASS with 30 IDs, five groups, and lossless Journey/selection/view/scroll history.
- [ ] **Commit scope.** Run `git add desktop/lib/navigation/app_route.dart desktop/lib/navigation/destination_catalog.dart desktop/lib/navigation/navigation_controller.dart desktop/test/navigation_catalog_test.dart desktop/test/navigation_controller_test.dart desktop/test/deep_link_test.dart && git commit -m "feat: add stable desktop routes"`.

### Task P4-T2: Add grouped navigation, search, palette, and retained views

**Files:**
- Create: `desktop/lib/navigation/view_cache.dart`
- Create: `desktop/lib/widgets/command_palette.dart`
- Create: `desktop/lib/widgets/nav_group.dart`
- Create: `desktop/lib/widgets/nav_search_field.dart`
- Modify: `desktop/lib/widgets/flywheel_nav.dart`
- Modify: `desktop/lib/widgets/side_rail.dart`
- Modify: `desktop/lib/shell/flywheel_shell.dart`
- Modify: `desktop/lib/shell/view_factory.dart`
- Test: `desktop/test/navigation_reachability_test.dart`
- Test: `desktop/test/command_palette_test.dart`
- Test: `desktop/test/navigation_state_test.dart`

**Interfaces:**
- Consumes: P4-T1 catalog/controller and every destination builder; no view may route by display label.
- Produces: `ViewCache.viewFor(AppLocation)`, `CommandPalette(controller,catalog)`, and typed `FlywheelNav.goTo(DestinationId, {AppLocation? location})`.

- [ ] **Write RED tests.** Reach all 30 destinations from expanded rail, collapsed rail, search, and Ctrl+K palette; verify Arrow keys, Enter, Escape, focus return, empty search, and label aliases; switch away and back while preserving active Journey, selection, view-local state, dirty Code session, and scroll offset.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/navigation_reachability_test.dart test/command_palette_test.dart test/navigation_state_test.dart`; expect failures for label routing, old groups, and rebuilt view state.
- [ ] **Implement minimal GREEN.** Render headers from the five catalog groups, search stable label/aliases without changing IDs, cache keyed destination subtrees with `PageStorageBucket`, and move group/search rendering to `nav_group.dart`/`nav_search_field.dart`; keep rail, shell, and view-factory files below 300 lines.
- [ ] **Verify.** Run the RED command and `flutter analyze`; expect PASS and no route or state keyed by a mutable label.
- [ ] **Commit scope.** Run `git add desktop/lib/navigation/view_cache.dart desktop/lib/widgets/command_palette.dart desktop/lib/widgets/nav_group.dart desktop/lib/widgets/nav_search_field.dart desktop/lib/widgets/flywheel_nav.dart desktop/lib/widgets/side_rail.dart desktop/lib/shell/flywheel_shell.dart desktop/lib/shell/view_factory.dart desktop/test/navigation_reachability_test.dart desktop/test/command_palette_test.dart desktop/test/navigation_state_test.dart && git commit -m "feat: group and search desktop navigation"`.

### Task P4-T3: Complete the semantic, keyboard, and focus audit

**Files:**
- Create: `desktop/lib/accessibility/action_registry.dart`
- Modify: `desktop/lib/ide/agent_runs_panel.dart`
- Modify: `desktop/lib/ide/file_tree.dart`
- Modify: `desktop/lib/ide/lint_index_sheet.dart`
- Modify: `desktop/lib/ide/open_panel.dart`
- Modify: `desktop/lib/ide/tab_bar.dart`
- Modify: `desktop/lib/views/agent_mode_pane.dart`
- Modify: `desktop/lib/views/discourse_view.dart`
- Modify: `desktop/lib/views/receipts_view.dart`
- Modify: `desktop/lib/widgets/appearance_panel.dart`
- Modify: `desktop/lib/widgets/chat_sidebar.dart`
- Modify: `desktop/lib/widgets/chat_thread.dart`
- Modify: `desktop/lib/widgets/fw.dart`
- Modify: `desktop/lib/widgets/graph_canvas.dart`
- Modify: `desktop/lib/widgets/mode_chip.dart`
- Modify: `desktop/lib/widgets/model_picker.dart`
- Modify: `desktop/lib/widgets/model_selector.dart`
- Modify: `desktop/lib/widgets/plugin_forms.dart`
- Modify: `desktop/lib/widgets/science_history.dart`
- Modify: `desktop/lib/widgets/side_rail.dart`
- Modify: `desktop/lib/widgets/split_pane.dart`
- Modify: `desktop/lib/widgets/status_bar.dart`
- Modify: `desktop/lib/widgets/tool_call_sheet.dart`
- Modify: `desktop/lib/widgets/usage_receipt_panel.dart`
- Modify: `desktop/lib/widgets/workflow_cards.dart`
- Test: `desktop/test/accessibility_actions_test.dart`
- Test: `desktop/test/keyboard_navigation_test.dart`
- Test: `desktop/test/focus_visibility_test.dart`

**Interfaces:**
- Consumes: Phase 3 `AccessibleAction` and P4-T1 stable IDs.
- Produces: `ActionRegistry` entries with stable semantic label, tooltip, shortcut, enabled reason, invoke callback, and focus order for every interactive control.

- [ ] **Write RED tests.** Scan each listed surface for unlabeled tap/drag handlers; invoke buttons with Enter/Space, menus with arrows/Escape, splitters with keyboard increments, and graph nodes through a semantic list fallback; assert disabled actions state why and focus remains visible/restored after dialogs.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/accessibility_actions_test.dart test/keyboard_navigation_test.dart test/focus_visibility_test.dart`; expect failures for the remaining raw pointer-only actions.
- [ ] **Implement minimal GREEN.** Register and render each action through semantic/focus primitives, preserve pointer behavior, add ordered focus traversal, provide keyboard alternatives for drag gestures, and extract focused widgets rather than growing files near 300 lines.
- [ ] **Verify.** Run the RED command and `flutter analyze`; expect PASS with no interactive control lacking an accessible name and keyboard action.
- [ ] **Commit scope.** Run `git add desktop/lib/accessibility/action_registry.dart desktop/lib/ide/agent_runs_panel.dart desktop/lib/ide/file_tree.dart desktop/lib/ide/lint_index_sheet.dart desktop/lib/ide/open_panel.dart desktop/lib/ide/tab_bar.dart desktop/lib/views/agent_mode_pane.dart desktop/lib/views/discourse_view.dart desktop/lib/views/receipts_view.dart desktop/lib/widgets/appearance_panel.dart desktop/lib/widgets/chat_sidebar.dart desktop/lib/widgets/chat_thread.dart desktop/lib/widgets/fw.dart desktop/lib/widgets/graph_canvas.dart desktop/lib/widgets/mode_chip.dart desktop/lib/widgets/model_picker.dart desktop/lib/widgets/model_selector.dart desktop/lib/widgets/plugin_forms.dart desktop/lib/widgets/science_history.dart desktop/lib/widgets/side_rail.dart desktop/lib/widgets/split_pane.dart desktop/lib/widgets/status_bar.dart desktop/lib/widgets/tool_call_sheet.dart desktop/lib/widgets/usage_receipt_panel.dart desktop/lib/widgets/workflow_cards.dart desktop/test/accessibility_actions_test.dart desktop/test/keyboard_navigation_test.dart desktop/test/focus_visibility_test.dart && git commit -m "fix: make desktop actions keyboard accessible"`.

### Task P4-T4: Honor 200 percent scale, high contrast, and reduced motion

**Files:**
- Create: `desktop/lib/accessibility/display_preferences.dart`
- Create: `desktop/lib/accessibility/motion.dart`
- Modify: `desktop/lib/theme/flywheel_theme.dart`
- Modify: `desktop/lib/theme/tokens.dart`
- Modify: `desktop/lib/app.dart`
- Modify: `desktop/lib/views/agent_view.dart`
- Modify: `desktop/lib/widgets/chat_thread.dart`
- Modify: `desktop/lib/widgets/side_rail.dart`
- Modify: `desktop/lib/widgets/graph_canvas.dart`
- Modify: `desktop/lib/widgets/split_pane.dart`
- Test: `desktop/test/display_accessibility_test.dart`
- Test: `desktop/test/high_contrast_test.dart`
- Test: `desktop/test/reduced_motion_test.dart`
- Test: `desktop/test/scale_200_smoke_test.dart`

**Interfaces:**
- Consumes: Phase 3 `SystemTextScaler`, verdict tokens, and connection text/icon states.
- Produces: `DisplayPreferences.fromMediaQuery`, `motionDuration(context, normal)`, and high-contrast token variants that do not change verdict semantics.

- [ ] **Write RED tests.** Pump Journey, Chat, Code, Receipts, rail, and palette at system scale 2.0; assert no clipped critical action or hidden semantics; high contrast measures at least 4.5:1 for normal text and 3:1 for large text, icons, focus indicators, and component boundaries; reduced motion makes every audited animation duration zero and preserves final state/focus.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/display_accessibility_test.dart test/high_contrast_test.dart test/reduced_motion_test.dart test/scale_200_smoke_test.dart`; expect overflow, fixed-duration, or measured-contrast failures.
- [ ] **Implement minimal GREEN.** Use flexible/wrapping layouts, consume `MediaQuery.highContrast` and `disableAnimations`, centralize duration selection, meet the measured 4.5:1 and 3:1 thresholds, and keep color verdict-only with text/icon labels in every mode.
- [ ] **Verify.** Run the RED command and `flutter analyze`; expect PASS at 200 percent, high contrast, and reduced motion.
- [ ] **Commit scope.** Run `git add desktop/lib/accessibility/display_preferences.dart desktop/lib/accessibility/motion.dart desktop/lib/theme/flywheel_theme.dart desktop/lib/theme/tokens.dart desktop/lib/app.dart desktop/lib/views/agent_view.dart desktop/lib/widgets/chat_thread.dart desktop/lib/widgets/side_rail.dart desktop/lib/widgets/graph_canvas.dart desktop/lib/widgets/split_pane.dart desktop/test/display_accessibility_test.dart desktop/test/high_contrast_test.dart desktop/test/reduced_motion_test.dart desktop/test/scale_200_smoke_test.dart && git commit -m "fix: honor assistive display preferences"`.

### Task P4-T5: Build the typed Recovery Center

**Files:**
- Create: `desktop/lib/models/recovery_item.dart`
- Create: `desktop/lib/services/recovery_catalog.dart`
- Create: `desktop/lib/services/failed_update_recovery_source.dart`
- Create: `desktop/lib/views/recovery_center.dart`
- Create: `desktop/lib/widgets/recovery_item_card.dart`
- Modify: `desktop/lib/shell/flywheel_shell.dart`
- Modify: `desktop/lib/widgets/status_bar.dart`
- Test: `desktop/test/recovery_catalog_test.dart`
- Test: `desktop/test/recovery_center_test.dart`

**Interfaces:**
- Consumes: Phase 2 Journey drafts/session; Phase 3 chat/code journals, operation snapshots, and Phase 1 migration/recovery reports.
- Produces: `RecoveryKind.unsentChat|dirtyCode|pendingJourney|interruptedOperation|incompleteMigration|failedUpdate`, `RecoveryItem`, `RecoveryAction`, `RecoverySource.load()`, and `RecoveryCatalog.refresh/perform`.

- [ ] **Write RED tests.** Load all six kinds; allow only state-valid actions: chat restore/discard, code inspect/digest-safe restore/discard, Journey open/retry-after-fresh-admission, operation inspect/request-cancel when advertised, migration read-only repair/export diagnostics, update inspect/rollback when verified. Assert no automatic deletion and no evidence/head change without a new admitted server event.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/recovery_catalog_test.dart test/recovery_center_test.dart`; expect missing-model/service failures.
- [ ] **Implement minimal GREEN.** Aggregate injected sources, keep items until explicit successful action, expose the center from shell/status/palette rather than route 31, and make the failed-update adapter return an empty typed result until Phase 6 writes compatible records; Phase 6 is not a prerequisite.
- [ ] **Verify.** Run the RED command and `flutter analyze`; expect PASS for valid/invalid actions, conflict preservation, and evidence immutability.
- [ ] **Commit scope.** Run `git add desktop/lib/models/recovery_item.dart desktop/lib/services/recovery_catalog.dart desktop/lib/services/failed_update_recovery_source.dart desktop/lib/views/recovery_center.dart desktop/lib/widgets/recovery_item_card.dart desktop/lib/shell/flywheel_shell.dart desktop/lib/widgets/status_bar.dart desktop/test/recovery_catalog_test.dart desktop/test/recovery_center_test.dart && git commit -m "feat: add typed recovery center"`.

### Task P4-T6: Seal navigation, accessibility, and recovery acceptance

**Files:**
- Create: `desktop/test/desktop_accessibility_e2e_test.dart`
- Create: `project-docs/records/2026-08-14-desktop-phase-4-navigation-accessibility.md`
- Modify: `desktop/test/widget_test.dart`
- Test: `desktop/test/navigation_reachability_test.dart`
- Test: `desktop/test/recovery_center_test.dart`

**Interfaces:**
- Consumes: P4-T1 through P4-T5 and all Phase 2/3 regression suites.
- Produces: a Phase 4 record binding source/tree hashes to route count, semantic action count, critical-flow matrix, display modes, recovery-kind/action denominators, limitations, and `does_not_prove`.

- [ ] **Write RED acceptance.** Exercise Journey create/resume, Chat draft restore, Code dirty-close recovery, receipt verification, operation cancellation, all 30 routes, search/history, keyboard-only navigation, semantics, focus, 200 percent scaling, high contrast, and reduced motion in one deterministic widget suite.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/desktop_accessibility_e2e_test.dart`; expect failure until every Phase 4 behavior and record exists.
- [ ] **Implement minimal GREEN.** Add deterministic fakes and the evidence record; report exact denominators and skips, do not infer screen-reader product behavior beyond semantics tests, and retain recovery data indefinitely until explicit user discard or successful restore.
- [ ] **Verify.** From `desktop/`, run `flutter analyze` and `flutter test`; expect exit 0. From repo root run `python scripts/check_file_gate.py`, `python scripts/check_claim_language.py`, `python scripts/check_public_instructions.py`, `python scripts/check_writing.py --profile procedure --gate project-docs/records/2026-08-14-desktop-phase-4-navigation-accessibility.md`, and `git diff --check`; expect exit 0 with exactly 30 routes and no route 31.
- [ ] **Commit scope.** Run `git add desktop/test/desktop_accessibility_e2e_test.dart desktop/test/widget_test.dart project-docs/records/2026-08-14-desktop-phase-4-navigation-accessibility.md && git commit -m "test: accept accessible desktop recovery"`.
