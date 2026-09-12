import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_launch_tour.dart';
import 'package:flywheel_desktop/widgets/rowan_presenter.dart';

/// A launcher button so the dialog is pushed inside a real Navigator with a
/// live BuildContext, the way the shell pushes it.
Widget _host({VoidCallback? onOpenStudio}) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: ElevatedButton(
              onPressed: () =>
                  showRowanWalkthrough(context, onOpenStudio: onOpenStudio),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );

void main() {
  testWidgets('opens on the avatar step and reaches the last step', (
    tester,
  ) async {
    // The shell always supplies onOpenStudio, so the last step offers the
    // Studio bridge; mirror that here.
    await tester.pumpWidget(_host(onOpenStudio: () {}));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    // Step one leads with the shader avatar, self-contained and engine-free.
    expect(find.byType(RowanPresenter), findsOneWidget);
    expect(find.text("I'm Rowan."), findsOneWidget);
    expect(find.text('Step 1 of 9'), findsOneWidget);
    expect(find.text('Back'), findsNothing);

    // Walk to the end; the avatar only appears on the first step.
    for (var i = 0; i < 8; i++) {
      await tester.tap(find.text('Next'));
      await tester.pumpAndSettle();
    }
    expect(find.text('Step 9 of 9'), findsOneWidget);
    expect(find.byType(RowanPresenter), findsNothing);
    expect(find.text('Next'), findsNothing);
    expect(find.text('Explore the Studio'), findsOneWidget);
  });

  testWidgets('the honest-null step keeps the not-claimed boundary visible', (
    tester,
  ) async {
    await tester.pumpWidget(_host());
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    for (var i = 0; i < 5; i++) {
      await tester.tap(find.text('Next'));
      await tester.pumpAndSettle();
    }
    expect(find.textContaining('written down as unknown'), findsOneWidget);
    expect(find.textContaining('tested, not proven adopted'), findsOneWidget);
  });

  testWidgets('the last step routes to the Studio and pops the dialog', (
    tester,
  ) async {
    var studioOpened = 0;
    await tester.pumpWidget(_host(onOpenStudio: () => studioOpened += 1));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    for (var i = 0; i < 8; i++) {
      await tester.tap(find.text('Next'));
      await tester.pumpAndSettle();
    }
    await tester.tap(find.text('Explore the Studio'));
    await tester.pumpAndSettle();
    expect(studioOpened, 1);
    expect(find.byType(RowanWalkthroughTour), findsNothing);
  });

  testWidgets('Skip dismisses from any step', (tester) async {
    await tester.pumpWidget(_host());
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Skip'));
    await tester.pumpAndSettle();
    expect(find.byType(RowanWalkthroughTour), findsNothing);
  });

  testWidgets('with no Studio callback the last step still offers Done', (
    tester,
  ) async {
    await tester.pumpWidget(_host());
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    for (var i = 0; i < 8; i++) {
      await tester.tap(find.text('Next'));
      await tester.pumpAndSettle();
    }
    expect(find.text('Explore the Studio'), findsNothing);
    await tester.tap(find.text('Done'));
    await tester.pumpAndSettle();
    expect(find.byType(RowanWalkthroughTour), findsNothing);
  });

  test('a brand-new install defaults firstRunSeen to false so the tour shows',
      () {
    // load() returns a default DesktopSettings when no file exists, and the
    // shell gates the first-run tour on !firstRunSeen. The constructor default
    // is what makes a fresh install present the tour once.
    expect(DesktopSettings().firstRunSeen, isFalse);
    expect(DesktopSettings(firstRunSeen: true).firstRunSeen, isTrue);
  });
}
