import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_controller.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_models.dart';

import 'rowan_action_cue_controller_fixtures.dart';

void main() {
  test('muting during pending playback suppresses late telemetry and caption',
      () async {
    final player = PendingActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );

    final future = controller.handle(event);
    await player.firstPlayStarted.future;
    controller.setMuted(true);
    player.releasePlay.complete();
    final decision = await future;

    expect(player.stops, 1);
    expect(decision.outcome, RowanActionCueOutcome.suppressed);
    expect(controller.telemetry, isEmpty);
    expect(controller.captions.value, isNull);
  });

  test('concurrent duplicate event is reserved before playback starts',
      () async {
    final player = PendingActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );

    final first = controller.handle(event);
    await player.firstPlayStarted.future;
    final second = await controller.handle(event);

    expect(second.reason, RowanActionCueReason.duplicateEvent);
    expect(player.played, hasLength(1));
    player.releasePlay.complete();
    await first;
  });

  test('playback failure does not emit played telemetry or caption', () async {
    final controller = RowanActionCueController(
      player: FailingActionCuePlayer(),
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );

    final decision = await controller.handle(event);

    expect(decision.outcome, RowanActionCueOutcome.suppressed);
    expect(decision.reason, RowanActionCueReason.playbackFailed);
    expect(controller.telemetry, isEmpty);
    expect(controller.captions.value, isNull);
  });

  test('muting reports cancellation failure when native stop throws', () async {
    final player = ThrowingStopActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );

    await controller.handle(event);
    controller.setMuted(true);
    await Future<void>.delayed(Duration.zero);

    expect(controller.settings.muted, isTrue);
    expect(controller.cancellation.value.status,
        RowanActionCueCancellationStatus.failed);
    expect(
        controller.cancellation.value.message, contains('native stop failed'));
  });

  test('replacement cue reports cancellation failure before replaying',
      () async {
    final player = ThrowingStopActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );

    await controller.handle(event);
    final decision = await controller.replay(event);

    expect(decision.outcome, RowanActionCueOutcome.suppressed);
    expect(decision.reason, RowanActionCueReason.cancellationFailed);
    expect(player.played, hasLength(1));
    expect(controller.cancellation.value.status,
        RowanActionCueCancellationStatus.failed);
  });
  test('dispose cancels pending playback before late completion can emit',
      () async {
    final player = PendingActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );

    final future = controller.handle(event);
    await player.firstPlayStarted.future;
    await controller.dispose();
    player.releasePlay.complete();
    final decision = await future;

    expect(player.stops, 1);
    expect(decision.outcome, RowanActionCueOutcome.suppressed);
    expect(decision.reason, RowanActionCueReason.playbackCancelled);
    expect(controller.telemetry, isEmpty);
    expect(controller.captions.value, isNull);
  });

  test('handle and replay after dispose never start playback', () async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );

    await controller.dispose();
    final handled = await controller.handle(event);
    final replayed = await controller.replay(event);

    expect(handled.outcome, RowanActionCueOutcome.suppressed);
    expect(handled.reason, RowanActionCueReason.playbackCancelled);
    expect(replayed.outcome, RowanActionCueOutcome.suppressed);
    expect(replayed.reason, RowanActionCueReason.playbackCancelled);
    expect(player.played, isEmpty);
    expect(player.stops, isZero);
  });

  test('settings changes after dispose do not touch player or notifiers',
      () async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );

    await controller.dispose();
    controller.setMuted(true);
    controller.setEnabled(false);

    expect(controller.settings.enabled, isTrue);
    expect(controller.settings.muted, isFalse);
    expect(controller.cancellation.value.status,
        RowanActionCueCancellationStatus.idle);
    expect(player.stops, isZero);
  });
}
