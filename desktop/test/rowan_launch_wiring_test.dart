// Shell-level coverage for the first-run walkthrough wiring. The tour widget
// has its own unit tests; this file proves the SHELL raises it exactly once on
// a first run and never on a returning run, and that it records the run by
// setting firstRunSeen and saving. Steady-state harness tests suppress the
// modal with firstRunSeen: true, so without this file the auto-present path
// would go uncovered.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/widgets/rowan_launch_tour.dart';
import 'journey_shell_harness.dart' show ShellHarness, unmount;

void main() {
  testWidgets('a first run raises the walkthrough and records that it ran',
      (tester) async {
    final directory = Directory.systemTemp.createTempSync('first-run-shell-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final harness = ShellHarness(directory, firstRunSeen: false)..replyReady();

    await tester.pumpWidget(harness.app());
    await tester.pumpAndSettle();

    expect(find.byType(RowanWalkthroughTour), findsOneWidget,
        reason: 'a brand-new install must present the tour once');
    // The flag is set on present, not on completion, so a force-quit mid-tour
    // does not make it reappear; and the shell saves so the flag survives.
    expect(harness.settings.firstRunSeen, isTrue);
    expect(harness.settings.saves, greaterThanOrEqualTo(1));

    await unmount(tester);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a returning run does not raise the walkthrough',
      (tester) async {
    final directory = Directory.systemTemp.createTempSync('return-run-shell-');
    addTearDown(() => directory.deleteSync(recursive: true));
    // Default firstRunSeen: true is the returning-user state.
    final harness = ShellHarness(directory)..replyReady();

    await tester.pumpWidget(harness.app());
    await tester.pumpAndSettle();

    expect(find.byType(RowanWalkthroughTour), findsNothing,
        reason: 'a returning user must not see the first-run tour again');

    await unmount(tester);
    expect(tester.takeException(), isNull);
  });
}
