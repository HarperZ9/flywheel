import 'dart:ui' show Tristate;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/journey_cards.dart';
import 'package:flywheel_desktop/widgets/journey_lenses.dart';

import 'journey_view_test.dart';
import 'journey_controller_test.dart' show headA, journeyA;

void main() {
  _semanticsAndFocusTests();
  _keyboardTests();
  _motionAndNarrowTests();
  _nullTests();
  _conclusionNullTests();
}

void _semanticsAndFocusTests() {
  testWidgets('selector has equal button semantics and one selected lens',
      (tester) async {
    final semantics = tester.ensureSemantics();
    final harness = await readyViewHarness();
    await tester.pumpWidget(journeyApp(harness));
    final nodes = [
      for (final label in const ['Rescue', 'Diagnose', 'Verify'])
        tester.getSemantics(find.bySemanticsLabel(label)),
    ];
    expect(nodes.every((node) => node.flagsCollection.isButton), isTrue);
    expect(
      tester.getSemantics(find.bySemanticsLabel('Diagnose')),
      matchesSemantics(
        label: 'Diagnose',
        isButton: true,
        hasSelectedState: true,
        hasEnabledState: true,
        isEnabled: true,
        hasTapAction: true,
      ),
    );
    expect(
        nodes.where(
            (node) => node.flagsCollection.isSelected == Tristate.isTrue),
        hasLength(1));
    final widths = [
      for (final lens in const ['rescue', 'diagnose', 'verify'])
        tester.getSize(find.byKey(ValueKey('journey-lens-$lens'))).width,
    ];
    expect(widths.toSet(), hasLength(1));
    expect(find.bySemanticsLabel('Event head $headA'), findsOneWidget);
    harness.api.reply('resume:$journeyA:diagnose',
        viewProjection(lens: JourneyLens.diagnose));
    tester.semantics.tap(find.semantics.byLabel('Diagnose'));
    await tester.pumpAndSettle();
    expect(
        tester
            .getSemantics(find.bySemanticsLabel('Diagnose'))
            .flagsCollection
            .isSelected,
        Tristate.isTrue);
    semantics.dispose();
  });

  testWidgets('focused selector resolves a neutral two pixel boundary',
      (tester) async {
    final harness = await readyViewHarness();
    await tester.pumpWidget(journeyApp(harness));
    final button = tester.widget<OutlinedButton>(
        find.byKey(const ValueKey('journey-lens-rescue')));
    final side = button.style!.side!.resolve({WidgetState.focused})!;
    expect(side.width, 2);
    expect(side.color, FwTokens.light.ink);
    expect(button.style!.minimumSize!.resolve({})!.height,
        greaterThanOrEqualTo(44));
  });
}

void _keyboardTests() {
  testWidgets('Tab arrows Home End and native activation are deterministic',
      (tester) async {
    var selected = JourneyLens.rescue;
    final activations = <JourneyLens>[];
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: StatefulBuilder(builder: (context, setState) {
        return Scaffold(
          body: JourneyLensSelector(
            selectedLens: selected,
            onSelected: (lens) async {
              activations.add(lens);
              setState(() => selected = lens);
            },
          ),
        );
      }),
    ));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    expect(_button(tester, 'rescue').focusNode!.hasFocus, isTrue);
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    expect(_button(tester, 'diagnose').focusNode!.hasFocus, isTrue);
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    expect(_button(tester, 'verify').focusNode!.hasFocus, isTrue);
    await tester.sendKeyEvent(LogicalKeyboardKey.home);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(selected, JourneyLens.diagnose);
    expect(_button(tester, 'diagnose').focusNode!.hasFocus, isTrue);
    await tester.sendKeyEvent(LogicalKeyboardKey.end);
    await tester.pump();
    expect(selected, JourneyLens.verify);
    await tester.sendKeyEvent(LogicalKeyboardKey.home);
    await tester.pump();
    expect(selected, JourneyLens.rescue);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pump();
    expect(selected, JourneyLens.diagnose);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pump();
    expect(activations.last, JourneyLens.diagnose);
    expect(activations.where((lens) => lens == JourneyLens.diagnose).length, 4);
  });
}

void _nullTests() {
  testWidgets('all empty lens collections retain bounded honest nulls',
      (tester) async {
    final empty = viewProjection(shape: 'empty');
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: Column(children: [
            JourneyCoreCard(projection: empty),
            RescueLens(
                projection:
                    viewProjection(lens: JourneyLens.rescue, shape: 'empty')),
            DiagnoseLens(
                projection:
                    viewProjection(lens: JourneyLens.diagnose, shape: 'empty')),
            VerifyLens(projection: empty),
          ]),
        ),
      ),
    ));
    for (final text in const [
      'No fact IDs were supplied in this projection.',
      'No claim IDs were supplied in this projection.',
      'No verdicts were supplied in this projection.',
      'No conclusion was supplied in this projection.',
      'No next action was supplied in this projection.',
      'No rollback action was supplied in this projection.',
      'No PASS verdicts were supplied in this projection.',
      'No FAIL verdicts were supplied in this projection.',
      'No missing evidence was supplied in this projection.',
      'No checks were supplied in this projection.',
      'No receipt refs were supplied in this projection.',
      'No does_not_prove limits were supplied in this projection.',
      'The server supplied no lens detail.',
    ]) {
      expect(find.text(text), findsWidgets);
    }
  });

  testWidgets('missing raw check states do not synthesize UNVERIFIABLE',
      (tester) async {
    final check = JourneyCheck(
      checkId: 'check-null',
      claimId: 'claim-null',
      verdict: EvidenceVerdict.invalidResponse,
      rawVerdict: null,
      receiptRefs: const [],
      receiptState: ReceiptState.invalidResponse,
      rawReceiptState: null,
      numerator: 0,
      denominator: 0,
      doesNotProve: '',
      parseIssues: const [],
    );
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: CheckRecord(check: check)),
    ));
    expect(find.text('UNVERIFIABLE'), findsNothing);
    expect(
        find.text('No verdict was supplied for this check.'), findsOneWidget);
    expect(find.text('No receipt state was supplied for this check.'),
        findsOneWidget);
  });
}

void _conclusionNullTests() {
  testWidgets('partial and empty conclusions render exact honest nulls',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: SingleChildScrollView(
        child: Column(children: [
          JourneyCoreCard(
              projection: viewProjection(shape: 'partial-conclusion')),
          JourneyCoreCard(
              projection: viewProjection(shape: 'empty-conclusion')),
        ]),
      ),
    ));
    expect(find.text('Evidence remains incomplete.'), findsOneWidget);
    expect(find.text('No conclusion summary was supplied in this projection.'),
        findsOneWidget);
    expect(
        find.text(
            'No conclusion does_not_prove limit was supplied in this projection.'),
        findsNWidgets(2));
  });
}

OutlinedButton _button(WidgetTester tester, String lens) =>
    tester.widget(find.byKey(ValueKey('journey-lens-$lens')));

void _motionAndNarrowTests() {
  testWidgets('reduced motion makes the lens transition immediate',
      (tester) async {
    final harness = await readyViewHarness();
    await tester.pumpWidget(journeyApp(harness, reducedMotion: true));
    await reveal(tester, find.byKey(const ValueKey('journey-lens-switcher')));
    final switcher = tester.widget<AnimatedSwitcher>(
        find.byKey(const ValueKey('journey-lens-switcher')));
    expect(switcher.duration, Duration.zero);
    expect(find.text('check-pass'), findsOneWidget);
  });

  testWidgets('320 pixel surface stacks full targets without overflow',
      (tester) async {
    final harness = await readyViewHarness();
    await tester
        .pumpWidget(journeyApp(harness, width: 320, height: 1200, scale: 1.4));
    await reveal(tester, find.byKey(const ValueKey('journey-lens-rescue')));
    expect(tester.takeException(), isNull);
    final rects = [
      for (final lens in const ['rescue', 'diagnose', 'verify'])
        tester.getRect(find.byKey(ValueKey('journey-lens-$lens'))),
    ];
    expect(rects.every((rect) => rect.height >= 44), isTrue);
    expect(rects[0].top, lessThan(rects[1].top));
    expect(rects[1].top, lessThan(rects[2].top));
    expect(rects.map((rect) => rect.width).toSet(), hasLength(1));
    expect(tester.takeException(), isNull);
  });
}
