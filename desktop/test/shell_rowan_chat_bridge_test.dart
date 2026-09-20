import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_controller.dart';
import 'package:flywheel_desktop/ide/unsaved_work_guard.dart';
import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/shell/view_factory.dart';
import 'package:flywheel_desktop/views/agent_view.dart';

import 'journey_shell_harness.dart';
import 'rowan_action_cue_controller_fixtures.dart';

void main() {
  test('destination factory gives Chat the shared Rowan cue controller', () {
    final dir = Directory.systemTemp.createTempSync('shell-rowan-chat-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final shell = ShellHarness(dir);
    final actionCueController =
        RowanActionCueController(player: FakeActionCuePlayer());
    addTearDown(actionCueController.dispose);

    final inputs = DestinationInputs(
      client: shell.client,
      journey: shell.controller,
      rowanOperationHost: shell.rowanHost,
      actionCueController: actionCueController,
      code: shell.code,
      codeGuard: UnsavedWorkGuard(
        session: shell.code,
        prompt: (_) async => CloseChoice.cancel,
      ),
      alive: false,
      settings: shell.settings,
      chatStore: shell.chatStore,
      chatDraftStore: shell.chatDraftStore,
      onProbe: () {},
      onInstall: (_) async => const {},
    );

    final view = buildDestinationView(DestinationId.chat, inputs) as AgentView;

    expect(view.actionCueController, same(actionCueController));
  });
}
