import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_controller.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_event_binding.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_models.dart';

import 'rowan_action_cue_controller_fixtures.dart';
import 'rowan_action_cue_event_binding_fixtures.dart';

const _suppressedDecision = RowanActionCueDecision(
  outcome: RowanActionCueOutcome.suppressed,
  reason: RowanActionCueReason.noClip,
);

void main() {
  test('first local screen snapshot with receipt cues live screen and receipt',
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

    screen.observe(
      const RowanActionCueScreenSharingSnapshot.running(
        sessionRef: 'screen-session-first-receipt',
        origin: RowanActionCueObservationOrigin.localStart,
        providerReceiptRef: 'dlv_first1111111111111111111111111111',
      ),
    );
    await flushCueBinding();

    expect(player.played.map((p) => p.recordedClip!.eventId), [
      'privacy.live_screen_on',
      'model.provider_receipt',
    ]);
    expect(controller.telemetry.map((t) => t.eventRef).toSet(), hasLength(2));
    await binding.dispose();
    await controller.dispose();
    screen.dispose();
  });

  test(
      'stop arriving while same-snapshot start cue is pending suppresses stale receipt',
      () async {
    final screen = BindingScreenSharingSource(
      const RowanActionCueScreenSharingSnapshot.stopped(),
    );
    final player = PendingActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final binding = RowanActionCueEventBinding(
      operationHost: BindingOperationHost(),
      screenSharing: screen,
      controller: controller,
    );

    screen.observe(
      const RowanActionCueScreenSharingSnapshot.running(
        sessionRef: 'screen-session-pending-stop',
        origin: RowanActionCueObservationOrigin.localStart,
        providerReceiptRef: 'dlv_pendingstop111111111111111111111',
      ),
    );
    await player.firstPlayStarted.future;
    screen.observe(
      const RowanActionCueScreenSharingSnapshot.stopped(
        sessionRef: 'screen-session-pending-stop',
      ),
    );
    await Future<void>.delayed(Duration.zero);
    player.releasePlay.complete();
    await flushCueBinding();

    expect(player.played.map((p) => p.recordedClip!.eventId), [
      'privacy.live_screen_on',
      'privacy.live_screen_off',
    ]);
    await binding.dispose();
    await controller.dispose();
    screen.dispose();
  });

  test(
      'rapid stop and restart suppresses old receipt while allowing new session receipt',
      () async {
    final screen = BindingScreenSharingSource(
      const RowanActionCueScreenSharingSnapshot.stopped(),
    );
    final firstDispatchStarted = Completer<void>();
    final releaseFirstDispatch = Completer<void>();
    final observed = <String>[];
    var dispatchCount = 0;
    final binding = RowanActionCueEventBinding(
      operationHost: BindingOperationHost(),
      screenSharing: screen,
      controller: RowanActionCueController(
        player: FakeActionCuePlayer(),
        settings: const RowanActionCueSettings(enabled: true),
      ),
      dispatch: (RowanActionCueEvent event) async {
        observed.add(event.kind.wire);
        dispatchCount += 1;
        if (dispatchCount == 1) {
          firstDispatchStarted.complete();
          await releaseFirstDispatch.future;
        }
        return _suppressedDecision;
      },
    );

    screen.observe(
      const RowanActionCueScreenSharingSnapshot.running(
        sessionRef: 'screen-session-old',
        origin: RowanActionCueObservationOrigin.localStart,
        providerReceiptRef: 'dlv_old1111111111111111111111111111',
      ),
    );
    await firstDispatchStarted.future;
    screen.observe(
      const RowanActionCueScreenSharingSnapshot.stopped(
        sessionRef: 'screen-session-old',
      ),
    );
    await Future<void>.delayed(Duration.zero);
    screen.observe(
      const RowanActionCueScreenSharingSnapshot.running(
        sessionRef: 'screen-session-new',
        origin: RowanActionCueObservationOrigin.localStart,
        providerReceiptRef: 'dlv_new1111111111111111111111111111',
      ),
    );
    await Future<void>.delayed(Duration.zero);
    releaseFirstDispatch.complete();
    await flushCueBinding();

    expect(observed, [
      'privacy.live_screen_on',
      'privacy.live_screen_off',
      'privacy.live_screen_on',
      'model.provider_receipt',
    ]);
    await binding.dispose();
    screen.dispose();
  });

  test(
    'provider receipt cues once for an accepted local screen session',
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

      screen.observe(
        const RowanActionCueScreenSharingSnapshot.running(
          sessionRef: 'screen-session-receipt',
          origin: RowanActionCueObservationOrigin.localStart,
        ),
      );
      await flushCueBinding();
      screen.observe(
        const RowanActionCueScreenSharingSnapshot.running(
          sessionRef: 'screen-session-receipt',
          providerReceiptRef: 'dlv_11111111111111111111111111111111',
        ),
      );
      await flushCueBinding();
      screen.observe(
        const RowanActionCueScreenSharingSnapshot.running(
          sessionRef: 'screen-session-receipt',
        ),
      );
      await flushCueBinding();
      screen.observe(
        const RowanActionCueScreenSharingSnapshot.running(
          sessionRef: 'screen-session-receipt',
          providerReceiptRef: 'dlv_22222222222222222222222222222222',
        ),
      );
      await flushCueBinding();

      expect(player.played.map((p) => p.recordedClip!.eventId), [
        'privacy.live_screen_on',
        'model.provider_receipt',
      ]);
      expect(controller.telemetry.map((t) => t.eventRef).toSet(), hasLength(2));
      await binding.dispose();
      await controller.dispose();
      screen.dispose();
    },
  );

  test('preview-only screen updates do not cue provider receipt', () async {
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

    screen.observe(
      const RowanActionCueScreenSharingSnapshot.running(
        sessionRef: 'screen-session-preview-only',
        origin: RowanActionCueObservationOrigin.localStart,
      ),
    );
    await flushCueBinding();
    screen.observe(
      const RowanActionCueScreenSharingSnapshot.running(
        sessionRef: 'screen-session-preview-only',
      ),
    );
    await flushCueBinding();

    expect(player.played.map((p) => p.recordedClip!.eventId), [
      'privacy.live_screen_on',
    ]);
    await binding.dispose();
    await controller.dispose();
    screen.dispose();
  });

  test('failed delivery without accepted receipt does not cue provider receipt',
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

    screen.observe(
      const RowanActionCueScreenSharingSnapshot.running(
        sessionRef: 'screen-session-failed-delivery',
        origin: RowanActionCueObservationOrigin.localStart,
      ),
    );
    await flushCueBinding();
    screen.observe(
      const RowanActionCueScreenSharingSnapshot.running(
        sessionRef: 'screen-session-failed-delivery',
      ),
    );
    await flushCueBinding();

    expect(player.played.map((p) => p.recordedClip!.eventId), [
      'privacy.live_screen_on',
    ]);
    expect(
      controller.telemetry.map((t) => t.kind.wire),
      isNot(contains('model.provider_receipt')),
    );
    await binding.dispose();
    await controller.dispose();
    screen.dispose();
  });
}
