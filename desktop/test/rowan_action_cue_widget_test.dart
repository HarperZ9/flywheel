import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_controller.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_models.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_widget.dart';

import 'rowan_action_cue_controller_fixtures.dart';

void main() {
  testWidgets('controls opt in, mute, and show latest recorded caption',
      (tester) async {
    final controller = RowanActionCueController(player: FakeActionCuePlayer());
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: RowanActionCueControls(controller: controller)),
    ));

    expect(find.text('Rowan action cues'), findsOneWidget);
    expect(controller.settings.enabled, isFalse);

    await tester.tap(find.byKey(const Key('rowan-action-cues-enabled')));
    await tester.pump();
    expect(controller.settings.enabled, isTrue);

    await controller.handle(
      RowanActionCueEvent.fromOperationSnapshot(runningCueSnapshot()),
    );
    await tester.pump();
    expect(find.textContaining('Recorded cue:'), findsOneWidget);

    await tester.tap(find.byKey(const Key('rowan-action-cues-muted')));
    await tester.pump();
    expect(controller.settings.muted, isTrue);
  });

  testWidgets('controls expose failed cancellation as unknown audio state',
      (tester) async {
    final controller = RowanActionCueController(
      player: ThrowingStopActionCuePlayer(),
      settings: const RowanActionCueSettings(enabled: true),
    );
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: RowanActionCueControls(controller: controller)),
    ));
    await controller.handle(
      RowanActionCueEvent.fromOperationSnapshot(runningCueSnapshot()),
    );
    await tester.pump();

    await tester.tap(find.byKey(const Key('rowan-action-cues-muted')));
    await tester.pump();
    await tester.pump();

    expect(find.textContaining('Audio cancellation failed'), findsOneWidget);
    expect(find.textContaining('playback state unknown'), findsOneWidget);
  });
}
