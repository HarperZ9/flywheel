import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_clips.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_controller.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_models.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_player.dart';

import 'rowan_action_cue_controller_fixtures.dart';

void main() {
  test('opt-in disabled by default suppresses autoplay and telemetry',
      () async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(player: player);
    final event = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );

    final decision = await controller.handle(event);

    expect(decision.outcome, RowanActionCueOutcome.suppressed);
    expect(decision.reason, RowanActionCueReason.optInDisabled);
    expect(player.played, isEmpty);
    expect(controller.telemetry, isEmpty);
  });

  test('operation cue plays recorded clip with stable refs and hashes',
      () async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );

    final decision = await controller.handle(event);

    expect(decision.outcome, RowanActionCueOutcome.played);
    expect(decision.caption, startsWith('Recorded cue:'));
    expect(
      player.played.single.recordedClip!.clipId,
      'cartesia-rowan-action-pack/v1:operation.working',
    );
    expect(player.played.single.recordedClip!.eventId, 'operation.working');
    expect(
      player.played.single.recordedClip!.assetKey,
      'rowan/action-cues/cartesia-rowan-complete-pack/audio/cartesia-rowan-action-pack-working.wav',
    );
    expect(player.played.single.recordedClip!.assetKey,
        isNot(contains('mission-control')));
    expect(player.played.single.recordedClip!.assetKey, isNot(contains(':\\')));
    expect(player.played.single.source, RowanActionCueAudioSource.recordedClip);
    expect(player.played.single.mayTrainOrCloneFromAudio, isFalse);
    expect(player.played.single.useRestriction, contains('do not use'));
    expect(controller.telemetry.single.operationRef, fixtureOperation);
    expect(controller.telemetry.single.variantId, 'v1');
    expect(controller.telemetry.single.clipSelectionSha256, hasLength(64));
    expect(controller.telemetry.single.textSha256,
        player.played.single.textSha256);
    expect(controller.telemetry.single.audioSha256,
        player.played.single.audioSha256);
    expect(controller.telemetry.single.playbackProvenanceSha256,
        player.played.single.provenanceSha256);
    expect(controller.telemetry.single.eventSha256, hasLength(64));
    expect(controller.telemetry.single.clipSha256, hasLength(64));
    expect(controller.telemetry.single.captionSha256, hasLength(64));
    expect(controller.telemetry.single.provesTaskCorrectness, isFalse);
  });

  test('duplicate event and cooldown suppress repeat cues', () async {
    var now = DateTime.utc(2026, 9, 15, 12);
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      now: () => now,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final first = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );
    final second = RowanActionCueEvent.fromOperationSnapshot(
      cueSnapshot('running', head: fixtureHeadB, canCancel: true),
    );

    expect(
      (await controller.handle(first)).outcome,
      RowanActionCueOutcome.played,
    );
    expect(
      (await controller.handle(first)).reason,
      RowanActionCueReason.duplicateEvent,
    );
    expect(
      (await controller.handle(second)).reason,
      RowanActionCueReason.cooldown,
    );
    now = now.add(const Duration(seconds: 9));
    expect(
      (await controller.handle(second)).outcome,
      RowanActionCueOutcome.played,
    );
    expect(player.played, hasLength(2));
  });

  test('explicit replay stops active clip and labels recorded replay',
      () async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );

    await controller.handle(event);
    final replay = await controller.replay(event);

    expect(replay.outcome, RowanActionCueOutcome.replayed);
    expect(replay.caption, startsWith('Recorded replay:'));
    expect(player.stops, 1);
    expect(player.played, hasLength(2));
  });

  test('historic recovered operation event never autoplays', () async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      cueSnapshot('completed'),
      recovered: true,
    );

    final decision = await controller.handle(event);

    expect(decision.outcome, RowanActionCueOutcome.suppressed);
    expect(decision.reason, RowanActionCueReason.historicEvent);
    expect(player.played, isEmpty);
  });

  test('screen event refs reject path or url shaped payload values', () {
    expect(
      () => RowanActionCueEvent.fromScreen(
        screen: RowanActionScreen.assistantPanel,
        eventRef: 'assets/rowan.wav',
      ),
      throwsArgumentError,
    );
    expect(
      () => RowanActionCueEvent.fromScreen(
        screen: RowanActionScreen.assistantPanel,
        eventRef: 'https://example.invalid/clip.wav',
      ),
      throwsArgumentError,
    );
    expect(
      () => RowanActionCueEvent.fromStableEvent(
        kind: RowanActionCueKind.evaluationFinished,
        eventRef: '../audio/clip.wav',
      ),
      throwsArgumentError,
    );
  });

  test('completion cue says inspectable rather than verified or passed',
      () async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      cueSnapshot('completed'),
    );

    final decision = await controller.handle(event);

    expect(decision.caption, contains('ready to inspect'));
    expect(decision.caption, isNot(contains('passed')));
    expect(decision.caption, isNot(contains('verified complete')));
    expect(decision.telemetry!.provesTaskCorrectness, isFalse);
  });

  test('evaluation finished cue does not become a pass or safety claim',
      () async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromStableEvent(
      kind: RowanActionCueKind.evaluationFinished,
      eventRef: 'eval_result_20260915_01',
    );

    final decision = await controller.handle(event);

    expect(decision.caption, contains('The check has finished'));
    expect(decision.caption, contains('review the result'));
    expect(decision.caption, isNot(contains('safe')));
    expect(decision.caption, isNot(contains('passed')));
    expect(decision.telemetry!.provesTaskCorrectness, isFalse);
  });

  test('variant selection is deterministic from stable event ref', () async {
    final registry = RowanActionClipRegistry.byKind({
      RowanActionCueKind.operationWorking: [
        variantClip('a'),
        variantClip('b'),
      ],
    });
    final firstPlayer = FakeActionCuePlayer();
    final secondPlayer = FakeActionCuePlayer();
    final first = RowanActionCueController(
      player: firstPlayer,
      registry: registry,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final second = RowanActionCueController(
      player: secondPlayer,
      registry: registry,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromOperationSnapshot(
      runningCueSnapshot(),
    );

    final firstDecision = await first.handle(event);
    final secondDecision = await second.handle(event);

    expect(firstPlayer.played.single.recordedClip!.variantId,
        secondPlayer.played.single.recordedClip!.variantId);
    expect(firstDecision.telemetry!.clipSelectionSha256,
        secondDecision.telemetry!.clipSelectionSha256);
    expect(firstDecision.telemetry!.clipSha256,
        secondDecision.telemetry!.clipSha256);
  });

  test('local synthesis playback request carries caption provenance', () {
    final playback = RowanActionCuePlayback.localSynthesis(
      localSynthesisRef: 'local_qwen3_tts_probe_01',
      caption: 'I can say this locally.',
      textSha256: fixtureHeadA,
      audioSha256: fixtureHeadB,
    );

    expect(playback.source, RowanActionCueAudioSource.localSynthesis);
    expect(playback.recordedClip, isNull);
    expect(playback.captionSha256, hasLength(64));
    expect(playback.provenanceSha256, hasLength(64));
    expect(playback.mayTrainOrCloneFromAudio, isFalse);
  });
}
