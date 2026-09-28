import 'dart:async';

import 'package:flywheel_desktop/assistant/rowan_action_cue_clip_model.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_player.dart';
import 'package:flywheel_desktop/models/operation_models.dart';

const fixtureA = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const fixtureB = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const fixtureHeadA = '$fixtureA$fixtureA';
const fixtureHeadB = '$fixtureB$fixtureB';
const fixtureOperation = 'op_$fixtureA';
const fixtureJourney = 'jrn_$fixtureA';

OperationSnapshot cueSnapshot(
  String state, {
  String head = fixtureHeadA,
  bool canCancel = false,
}) =>
    OperationSnapshot.fromJson({
      'schema': operationSnapshotSchema,
      'operation_ref': fixtureOperation,
      'journey_ref': fixtureJourney,
      'event_head_sha256': head,
      'state': state,
      'can_cancel': canCancel,
      'terminal_event_ref': state == 'completed' ? fixtureHeadB : null,
      'result_sha256': state == 'completed' ? fixtureHeadA : null,
    });

OperationSnapshot runningCueSnapshot() => cueSnapshot(
      'running',
      canCancel: true,
    );

class FakeActionCuePlayer implements RowanActionCuePlayer {
  final played = <RowanActionCuePlayback>[];
  var stops = 0;

  @override
  Stream<void> get completions => const Stream.empty();

  @override
  Future<void> play(RowanActionCuePlayback playback) async {
    played.add(playback);
  }

  @override
  Future<void> stop() async {
    stops++;
  }
}

class PendingActionCuePlayer implements RowanActionCuePlayer {
  final played = <RowanActionCuePlayback>[];
  final firstPlayStarted = Completer<void>();
  final releasePlay = Completer<void>();
  var stops = 0;

  @override
  Stream<void> get completions => const Stream.empty();

  @override
  Future<void> play(RowanActionCuePlayback playback) async {
    played.add(playback);
    if (!firstPlayStarted.isCompleted) firstPlayStarted.complete();
    await releasePlay.future;
  }

  @override
  Future<void> stop() async {
    stops++;
  }
}

class FailingActionCuePlayer implements RowanActionCuePlayer {
  @override
  Stream<void> get completions => const Stream.empty();

  @override
  Future<void> play(RowanActionCuePlayback playback) async {
    throw StateError('native playback failed');
  }

  @override
  Future<void> stop() async {}
}

class ThrowingStopActionCuePlayer implements RowanActionCuePlayer {
  final played = <RowanActionCuePlayback>[];
  var stops = 0;

  @override
  Stream<void> get completions => const Stream.empty();

  @override
  Future<void> play(RowanActionCuePlayback playback) async {
    played.add(playback);
  }

  @override
  Future<void> stop() async {
    stops++;
    throw StateError('native stop failed');
  }
}

RowanActionClip variantClip(String variantId) => RowanActionClip(
      eventId: 'operation.working',
      clipId: 'test:operation.working:$variantId',
      variantId: variantId,
      assetKey: 'test/$variantId.wav',
      caption: 'Working variant $variantId.',
      category: 'operation',
      context: 'operation-state',
      prerequisite: 'Live operation progress observed.',
      trigger: 'Live operation progress observed.',
      textSha256: fixtureHeadA,
      audioSha256: fixtureHeadB,
      durationSeconds: 1,
      recommendedCooldownSeconds: 3,
      manifestSha256: fixtureHeadA,
      sourcePack: 'test-pack',
      generation: 'test',
      provenanceBasis: 'test-fixture',
    );
