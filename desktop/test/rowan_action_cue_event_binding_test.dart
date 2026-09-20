import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_controller.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_event_binding.dart';

import 'rowan_action_cue_controller_fixtures.dart';
import 'rowan_action_cue_event_binding_fixtures.dart';

void main() {
  test('operation binding is silent for initial recovered snapshot', () async {
    final host = BindingOperationHost()
      ..observe(snapshot: runningCueSnapshot(), active: true);
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final binding = RowanActionCueEventBinding(
      operationHost: host,
      controller: controller,
    );

    host.observe(snapshot: runningCueSnapshot(), active: true);
    await flushCueBinding();

    expect(player.played, isEmpty);
    expect(controller.telemetry, isEmpty);
    await binding.dispose();
    await controller.dispose();
    host.dispose();
  });

  test('operation binding emits start and terminal observations once',
      () async {
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
    host.observe(snapshot: runningCueSnapshot(), active: true);
    await flushCueBinding();
    host.observe(snapshot: cueSnapshot('completed'), active: false);
    await flushCueBinding();

    expect(player.played.map((p) => p.recordedClip!.eventId), [
      'operation.started',
      'operation.completed',
    ]);
    expect(controller.telemetry.first.eventRef, fixtureHeadA);
    expect(controller.telemetry.first.operationRef, fixtureOperation);
    expect(controller.telemetry.last.eventRef, fixtureHeadB);
    expect(controller.telemetry.last.provesTaskCorrectness, isFalse);
    await binding.dispose();
    await controller.dispose();
    host.dispose();
  });

  test('operation terminal failure and stopped states keep their own cue kinds',
      () async {
    final cases = <String, String>{
      'failed': 'operation.unable_to_complete',
      'cancelled': 'operation.stopped',
    };
    for (final entry in cases.entries) {
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
      host.observe(
        snapshot: bindingTerminalCueSnapshot(entry.key),
        active: false,
      );
      await flushCueBinding();

      expect(player.played.single.recordedClip!.eventId, entry.value);
      expect(controller.telemetry.single.provesTaskCorrectness, isFalse);
      await binding.dispose();
      await controller.dispose();
      host.dispose();
    }
  });

  test('dispose unsubscribes and pending operation callback stays silent',
      () async {
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

    host.observe(snapshot: runningCueSnapshot(), active: true);
    await binding.dispose();
    await flushCueBinding();
    host.observe(snapshot: cueSnapshot('completed'), active: false);
    await flushCueBinding();

    expect(host.removedListeners, 1);
    expect(player.played, isEmpty);
    expect(controller.telemetry, isEmpty);
    await controller.dispose();
    host.dispose();
  });

  test('screen binding emits active stopped and connection transitions',
      () async {
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
      sessionRef: 'screen-session-1',
      origin: RowanActionCueObservationOrigin.localStart,
    ));
    await flushCueBinding();
    screen.observe(const RowanActionCueScreenSharingSnapshot.disconnected(
      sessionRef: 'screen-session-1',
    ));
    await flushCueBinding();
    screen.observe(const RowanActionCueScreenSharingSnapshot.running(
      sessionRef: 'screen-session-1',
    ));
    await flushCueBinding();
    screen.observe(const RowanActionCueScreenSharingSnapshot.stopped(
      sessionRef: 'screen-session-1',
    ));
    await flushCueBinding();

    expect(player.played.map((p) => p.recordedClip!.eventId), [
      'privacy.live_screen_on',
      'connection.reconnecting',
      'connection.restored',
      'privacy.live_screen_off',
    ]);
    expect(
        controller.telemetry.map((t) => t.operationRef), everyElement(isNull));
    expect(controller.telemetry.map((t) => t.eventRef).toSet(), hasLength(4));
    await binding.dispose();
    await controller.dispose();
    screen.dispose();
  });

  test('screen pause is observed without false operation-pause cue', () async {
    final screen = BindingScreenSharingSource(
      const RowanActionCueScreenSharingSnapshot.running(
        sessionRef: 'screen-session-2',
      ),
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

    screen.observe(const RowanActionCueScreenSharingSnapshot.paused(
      sessionRef: 'screen-session-2',
    ));
    await flushCueBinding();

    expect(player.played, isEmpty);
    expect(controller.telemetry, isEmpty);
    await binding.dispose();
    await controller.dispose();
    screen.dispose();
  });

  test('dispatch failures are reported and do not escape listener callbacks',
      () async {
    final host = BindingOperationHost();
    final errors = <Object>[];
    final binding = RowanActionCueEventBinding(
      operationHost: host,
      controller: RowanActionCueController(
        player: FakeActionCuePlayer(),
        settings: const RowanActionCueSettings(enabled: true),
      ),
      dispatch: (_) async => throw StateError('cue dispatch failed'),
      onError: (error, _) => errors.add(error),
    );

    host.observe(authorizing: true);
    await flushCueBinding();
    host.observe(snapshot: runningCueSnapshot(), active: true);
    await flushCueBinding();

    expect(errors.single, isA<StateError>());
    await binding.dispose();
    host.dispose();
  });
}
