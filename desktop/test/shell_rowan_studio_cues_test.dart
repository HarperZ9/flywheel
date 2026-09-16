import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/live_screen_sharing.dart';
import 'package:flywheel_desktop/shell/shell_rowan_cues.dart';

import 'rowan_action_cue_controller_fixtures.dart';
import 'rowan_action_cue_event_binding_fixtures.dart';

void main() {
  test('studio navigation cue uses the shell controller for real studio opens',
      () async {
    final sharing =
        LiveScreenSharing(GatewayClient(baseUrl: 'https://cue.invalid'));
    final host = BindingOperationHost();
    final player = FakeActionCuePlayer();
    final cues = ShellRowanCues(
      operationHost: host,
      screenSharing: sharing,
      player: player,
    )..controller.setEnabled(true);

    await cues.studioOpened();
    await flushCueBinding();

    expect(player.played.map((playback) => playback.recordedClip!.eventId),
        ['studio.open']);
    expect(cues.controller.telemetry.single.provesTaskCorrectness, isFalse);
    await cues.dispose();
    sharing.dispose();
    host.dispose();
  });
}
