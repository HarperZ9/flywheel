import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_clips.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_complete_ids.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_controller.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_models.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_pack_provenance.dart';

import 'rowan_action_cue_controller_fixtures.dart';

void main() {
  const packRoot = 'assets/rowan/action-cues/cartesia-rowan-complete-pack';

  test('complete pack manifest and wav assets are packaged once', () {
    final manifestFile = File('$packRoot/manifest.json');
    expect(manifestFile.existsSync(), isTrue);
    final manifest = jsonDecode(manifestFile.readAsStringSync())
        as Map<String, Object?>;
    final clips = (manifest['clips']! as List<Object?>)
        .cast<Map<String, Object?>>();
    final audioFiles = Directory('$packRoot/audio')
        .listSync()
        .whereType<File>()
        .where((file) => file.path.endsWith('.wav'))
        .toList();

    expect(manifest['schema'], rowanCartesiaCompletePackSchema);
    expect(manifest['total_clip_count'], 186);
    expect(clips, hasLength(186));
    expect(audioFiles, hasLength(186));

    final audioRefs = <String>{};
    for (final clip in clips) {
      final audioFile = clip['audio_file']! as String;
      expect(audioRefs.add(audioFile), isTrue, reason: audioFile);
      expect(audioFile, isNot(contains('mission-control')));
      expect(audioFile, isNot(contains(':\\')));
      final bytes = File('$packRoot/$audioFile').readAsBytesSync();
      expect(sha256.convert(bytes).toString(), clip['audio_sha256']);
    }
  });

  test('registry resolves new complete cues and legacy cue constants', () async {
    final registry = RowanActionClipRegistry.cartesiaActionPack();

    final welcome = registry.clipFor(RowanCompleteActionCueEvents.onboardingWelcome)!;
    expect(welcome.eventId, 'onboarding.welcome');
    expect(welcome.caption, "Hi, I'm Rowan. What would you like to work on?");
    expect(welcome.assetKey,
        'rowan/action-cues/cartesia-rowan-complete-pack/audio/welcome.wav');
    expect(welcome.sourcePack, 'cartesia-rowan-complete-pack');
    expect(welcome.generation, 'new');
    expect(welcome.audioSha256, hasLength(64));
    expect(welcome.textSha256, hasLength(64));
    expect(welcome.provenanceBasis, isNotEmpty);

    final reaction = registry.clipFor(RowanCompleteActionCueEvents.reactionSteadySteps)!;
    expect(reaction.eventId, 'reaction.steady_steps');
    expect(reaction.category, 'reactions');

    final legacy = registry.clipFor(RowanActionCueKind.operationWorking)!;
    expect(legacy.eventId, 'operation.working');
    expect(legacy.assetKey,
        'rowan/action-cues/cartesia-rowan-complete-pack/audio/cartesia-rowan-action-pack-working.wav');
    expect(legacy.sourcePack, 'cartesia-rowan-action-pack');
    expect(legacy.generation, 'reused');
  });

  test('controller can play a manifest-backed complete cue safely', () async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final event = RowanActionCueEvent.fromStableEvent(
      kind: RowanCompleteActionCueEvents.privacySecretBoundary,
      eventRef: 'privacy_secret_boundary_20260915',
    );

    final decision = await controller.handle(event);

    expect(decision.outcome, RowanActionCueOutcome.played);
    expect(decision.telemetry!.toJson()['kind'], 'privacy.secret_boundary');
    expect(decision.telemetry!.provesTaskCorrectness, isFalse);
    expect(player.played.single.recordedClip!.caption,
        "Let's keep secrets out of this conversation.");
    expect(player.played.single.recordedClip!.assetKey,
        'rowan/action-cues/cartesia-rowan-complete-pack/audio/privacy-secret-boundary.wav');
    expect(player.played.single.mayTrainOrCloneFromAudio, isFalse);
  });
}
