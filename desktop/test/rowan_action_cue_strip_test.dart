import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_caption.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_player.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_strip.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';

RowanActionCueCaptionState caption(String event, {bool replay = false}) =>
    RowanActionCueCaptionState(
      caption: '${replay ? 'Recorded replay' : 'Recorded cue'}: Let us begin.',
      captionSha256: replay ? 'replay-caption' : 'caption',
      playbackProvenanceSha256: 'provenance',
      recordedReplay: replay,
      source: RowanActionCueAudioSource.recordedClip,
      eventRef: event,
    );

void main() {
  testWidgets(
      'caption is readable outside settings and dismissal keeps receipt',
      (tester) async {
    final captions = ValueNotifier<RowanActionCueCaptionState?>(null);
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: RowanActionCueStrip(captions: captions)),
    ));
    expect(find.byKey(const Key('rowan-cue-caption-strip')), findsNothing);
    final first = caption('event-1');
    captions.value = first;
    await tester.pump();
    expect(find.text(first.caption), findsOneWidget);
    await tester.tap(find.byTooltip('Dismiss Rowan caption'));
    await tester.pump();
    expect(find.text(first.caption), findsNothing);
    expect(captions.value, same(first));

    // A distinct event with identical wording must still be visible.
    captions.value = caption('event-2');
    await tester.pump();
    expect(find.text(first.caption), findsOneWidget);
    captions.value = caption('event-2', replay: true);
    await tester.pump();
    expect(find.textContaining('Recorded replay:'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    captions.dispose();
  });

  testWidgets('long caption fits a narrow screen with large text',
      (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final captions = ValueNotifier<RowanActionCueCaptionState?>(
      RowanActionCueCaptionState(
        caption:
            'Recorded cue: ${List.filled(35, 'Your work remains available.').join(' ')}',
        captionSha256: 'long',
        playbackProvenanceSha256: 'long-provenance',
        recordedReplay: false,
        source: RowanActionCueAudioSource.recordedClip,
      ),
    );
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: MediaQuery(
        data: const MediaQueryData(textScaler: TextScaler.linear(2)),
        child: Scaffold(body: RowanActionCueStrip(captions: captions)),
      ),
    ));
    expect(tester.takeException(), isNull);
    expect(find.byType(SingleChildScrollView), findsOneWidget);
    expect(
        tester.getSize(find.byKey(const Key('rowan-cue-caption-strip'))).height,
        lessThanOrEqualTo(160));
    await tester.tap(find.byTooltip('Dismiss Rowan caption'));
    await tester.pump();
    expect(find.byKey(const Key('rowan-cue-caption-strip')), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
    captions.dispose();
  });
}
