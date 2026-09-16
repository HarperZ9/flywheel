import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_controller.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_event_binding.dart';

import 'rowan_action_cue_controller_fixtures.dart';
import 'rowan_action_cue_event_binding_fixtures.dart';

void main() {
  test('late recovered operation snapshots after null baseline stay silent',
      () async {
    for (final snapshot in [runningCueSnapshot(), cueSnapshot('completed')]) {
      final host = BindingOperationHost();
      final player = FakeActionCuePlayer();
      final controller = RowanActionCueController(
        player: player,
        settings: const RowanActionCueSettings(enabled: true),
      );
      final binding = RowanActionCueEventBinding(
        operationHost: host,
        controller: controller,
      );

      host.observe(snapshot: snapshot, active: !snapshot.isTerminal);
      await flushCueBinding();

      expect(player.played, isEmpty);
      expect(controller.telemetry, isEmpty);
      await binding.dispose();
      await controller.dispose();
      host.dispose();
    }
  });

  test('actual local operation start after authorization still cues', () async {
    final host = BindingOperationHost();
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final binding = RowanActionCueEventBinding(
      operationHost: host,
      controller: controller,
    );

    host.observe(authorizing: true);
    await flushCueBinding();
    host.observe(snapshot: runningCueSnapshot(), active: true);
    await flushCueBinding();

    expect(player.played.single.recordedClip!.eventId, 'operation.started');
    expect(controller.telemetry.single.operationRef, fixtureOperation);
    await binding.dispose();
    await controller.dispose();
    host.dispose();
  });

  test('restored screen share after stopped baseline stays silent', () async {
    final screen = BindingScreenSharingSource(
      const RowanActionCueScreenSharingSnapshot.stopped(),
    );
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final binding = RowanActionCueEventBinding(
      operationHost: BindingOperationHost(),
      screenSharing: screen,
      controller: controller,
    );

    screen.observe(const RowanActionCueScreenSharingSnapshot.running(
      sessionRef: 'screen-session-restored',
      origin: RowanActionCueObservationOrigin.recovered,
    ));
    await flushCueBinding();

    expect(player.played, isEmpty);
    expect(controller.telemetry, isEmpty);
    await binding.dispose();
    await controller.dispose();
    screen.dispose();
  });

  test('actual local screen-share start still cues', () async {
    final screen = BindingScreenSharingSource(
      const RowanActionCueScreenSharingSnapshot.stopped(),
    );
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final binding = RowanActionCueEventBinding(
      operationHost: BindingOperationHost(),
      screenSharing: screen,
      controller: controller,
    );

    screen.observe(const RowanActionCueScreenSharingSnapshot.running(
      sessionRef: 'screen-session-local-start',
      origin: RowanActionCueObservationOrigin.localStart,
    ));
    await flushCueBinding();

    expect(
        player.played.single.recordedClip!.eventId, 'screen_sharing.started');
    expect(controller.telemetry.single.operationRef, isNull);
    await binding.dispose();
    await controller.dispose();
    screen.dispose();
  });
}
