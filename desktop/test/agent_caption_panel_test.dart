import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/agent_caption_panel.dart';
import 'agent_caption_fixtures.dart';

void main() {
  testWidgets(
      'private captions opt in, pause follow keeps receiving, close clears',
      (tester) async {
    var reads = 0;
    final pages = captionPages([
      captionLedger('assistant', 'first original'),
      captionLedger('assistant', 'second original')
    ]);
    final reader = CaptionReader((projection, sequence, cancelled) async {
      reads++;
      return captionPage(pages[sequence], sequence);
    });
    Widget app(int count) => MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: SingleChildScrollView(
                child: AgentCaptionPanel(
                    reader: reader,
                    projection: captionProjection(pages, count: count)))));
    await tester.pumpWidget(app(1));
    expect(reads, 0);
    expect(find.textContaining('Provider summary unavailable'), findsOneWidget);
    await tester.tap(find.text('Start private captions'));
    await tester.pumpAndSettle();
    expect(find.text('first original'), findsOneWidget);
    await tester.tap(find.text('Pause follow'));
    await tester.pumpWidget(app(2));
    await tester.pumpAndSettle();
    expect(reads, 2);
    expect(find.text('Resume follow'), findsOneWidget);
    expect(find.textContaining('2 records received'), findsOneWidget);
    await tester.tap(find.text('Close captions'));
    await tester.pumpAndSettle();
    expect(find.text('first original'), findsNothing);
    expect(find.text('second original'), findsNothing);
    expect(find.text('Start private captions'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('readable sizing and reduced motion work on a narrow surface',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final pages =
        captionPages([captionLedger('assistant', 'café original source ✓')]);
    final reader = CaptionReader((p, sequence, cancelled) async =>
        captionPage(pages[sequence], sequence));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: MediaQuery(
            data: const MediaQueryData(
                disableAnimations: true, textScaler: TextScaler.linear(1.5)),
            child: Scaffold(
                body: SingleChildScrollView(
                    child: AgentCaptionPanel(
                        reader: reader,
                        projection: captionProjection(pages)))))));
    await tester.ensureVisible(find.text('Start private captions'));
    await tester.tap(find.text('Start private captions'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byTooltip('Larger captions'));
    await tester.tap(find.byTooltip('Larger captions'));
    await tester.pumpAndSettle();
    expect(find.text('café original source ✓'), findsOneWidget);
    expect(find.textContaining('received'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
