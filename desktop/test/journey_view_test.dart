import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/journey_view.dart';
import 'package:flywheel_desktop/widgets/journey_lenses.dart';

import 'journey_controller_test.dart';

String lensWire(JourneyLens lens) => switch (lens) {
      JourneyLens.rescue => 'Rescue',
      JourneyLens.diagnose => 'Diagnose',
      _ => 'Verify',
    };

const _openCheck = <String, Object?>{
  'check_id': 'check-open',
  'claim_id': 'claim-open',
  'verdict': 'UNVERIFIABLE',
  'receipt_refs': ['receipt-unchecked'],
  'receipt_state': 'present_unchecked',
  'numerator': 0,
  'denominator': 1,
  'does_not_prove': 'This check does not prove the claim.',
};
const _richChecks = <Map<String, Object?>>[
  {
    'check_id': 'check-pass',
    'claim_id': 'claim-pass',
    'verdict': 'PASS',
    'receipt_refs': ['receipt-match'],
    'receipt_state': 'MATCH',
    'numerator': 2,
    'denominator': 2,
    'does_not_prove': 'This check does not prove completeness.',
  },
  _openCheck,
];
const _uncheckedChecks = <Map<String, Object?>>[_openCheck];

JourneyProjection viewProjection({
  JourneyLens lens = JourneyLens.verify,
  String shape = 'rich',
}) {
  final empty = shape == 'empty';
  final unchecked = shape == 'unchecked';
  return JourneyProjection.fromJson({
    'schema': 'flywheel.evidence-journey-projection/v2',
    'journey_ref': journeyA,
    'event_head_sha256': headA,
    'fact_ids': empty ? const [] : const ['fact-alpha', 'fact-beta'],
    'claim_ids': empty
        ? const []
        : unchecked
            ? const ['claim-open']
            : const ['claim-pass', 'claim-fail', 'claim-open'],
    'checks': empty
        ? const []
        : unchecked
            ? _uncheckedChecks
            : _richChecks,
    'verdicts': empty
        ? const {}
        : unchecked
            ? const {'claim-open': 'UNVERIFIABLE'}
            : const {
                'claim-pass': 'PASS',
                'claim-fail': 'FAIL',
                'claim-open': 'UNDECIDED',
              },
    'missing_evidence': empty || unchecked
        ? const []
        : const [
            {
              'kind': 'receipt',
              'id': 'missing-receipt',
              'receipt_refs': ['receipt-missing'],
            }
          ],
    'stage': 'running',
    'conclusion': empty
        ? null
        : const {
            'summary': 'Evidence remains incomplete.',
            'does_not_prove': 'This conclusion does not prove optimality.',
          },
    'next_actions': empty || unchecked
        ? const []
        : const [
            {
              'action_id': 'action-repair',
              'kind': 'repair',
              'description': 'Rebuild the evidence index.',
              'basis_refs': ['fact-alpha'],
            },
            {
              'action_id': 'action-rollback',
              'kind': 'rollback',
              'description': 'Restore the prior event head.',
              'basis_refs': ['receipt-match'],
            },
          ],
    'detail': empty ? '' : 'Server supplied ${lensWire(lens)} detail.',
    'lens': lensWire(lens),
  });
}

Future<ControllerHarness> readyViewHarness(
    {JourneyProjection? projection}) async {
  final api = ScriptedJourneyApi();
  final harness = ControllerHarness(api);
  addTearDown(harness.dispose);
  final initial = projection ?? viewProjection();
  harness.sessions
      .save(JourneySession(journeyRef: journeyA, lens: initial.lens!));
  api
    ..reply('resume:$journeyA:${initial.lens!.name}', initial)
    ..reply('list', <JourneySummary>[initial]);
  await harness.controller.initialize();
  api.calls.clear();
  return harness;
}

Widget journeyApp(ControllerHarness harness,
        {double width = 900,
        double height = 1000,
        double scale = 1,
        bool reducedMotion = false}) =>
    MaterialApp(
      theme: flywheelLightTheme(),
      home: MediaQuery(
        data: MediaQueryData(
          size: Size(width, height),
          textScaler: TextScaler.linear(scale),
          disableAnimations: reducedMotion,
        ),
        child: Scaffold(
          body: SizedBox(
            width: width,
            height: height,
            child: JourneyView(controller: harness.controller),
          ),
        ),
      ),
    );

Future<void> reveal(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 240,
      scrollable: find.byType(Scrollable).first);
  await tester.pumpAndSettle();
}

void main() {
  _sharedAndRescueTests();
  _diagnoseAndVerifyTests();
  _nullAndExtensionTests();
}

void _sharedAndRescueTests() {
  testWidgets('all lenses retain the shared server evidence record',
      (tester) async {
    final harness = await readyViewHarness();
    await tester.pumpWidget(journeyApp(harness));
    for (final lens in const [JourneyLens.rescue, JourneyLens.diagnose]) {
      harness.api
          .reply('resume:$journeyA:${lens.name}', viewProjection(lens: lens));
      await tester.tap(find.text(lensWire(lens)));
      await tester.pumpAndSettle();
      expect(find.text('aaaaaaaaaaaaaaaaaaaaaaaa…'), findsOneWidget);
      for (final value in const [
        'running',
        'fact-alpha',
        'fact-beta',
        'claim-pass',
        'claim-fail',
        'claim-open',
        'PASS',
        'FAIL',
        'UNDECIDED',
        'Evidence remains incomplete.',
      ]) {
        expect(find.text(value), findsWidgets, reason: '${lens.name}: $value');
      }
    }
  });

  testWidgets('Rescue preserves action fields and exact rollback',
      (tester) async {
    final harness = await readyViewHarness(
        projection: viewProjection(lens: JourneyLens.rescue));
    await tester.pumpWidget(journeyApp(harness));
    await reveal(tester, find.text('Rebuild the evidence index.'));
    for (final value in const [
      'Rebuild the evidence index.',
      'action-repair',
      'repair',
      'fact-alpha',
      'Restore the prior event head.',
      'action-rollback',
      'rollback',
      'receipt-match',
    ]) {
      expect(find.text(value), findsWidgets);
    }
  });
}

void _diagnoseAndVerifyTests() {
  testWidgets('Diagnose separates exact verdict and missing evidence groups',
      (tester) async {
    final harness = await readyViewHarness(
        projection: viewProjection(lens: JourneyLens.diagnose));
    await tester.pumpWidget(journeyApp(harness));
    await reveal(tester, find.text('Support'));
    for (final value in const [
      'Support',
      'claim-pass',
      'Contradictions',
      'claim-fail',
      'Unresolved',
      'claim-open',
      'UNDECIDED',
      'Missing evidence',
      'receipt',
      'missing-receipt',
      'receipt-missing',
    ]) {
      expect(find.text(value), findsWidgets);
    }
  });

  testWidgets('Verify shows exact check custody and bounded limits',
      (tester) async {
    final harness = await readyViewHarness();
    await tester.pumpWidget(journeyApp(harness));
    await reveal(tester, find.text('check-pass'));
    for (final value in const [
      'check-pass',
      'claim-pass',
      '2 / 2',
      'MATCH',
      'receipt-match',
      'This check does not prove completeness.',
      'This conclusion does not prove optimality.',
    ]) {
      expect(find.text(value), findsWidgets);
    }
  });

  testWidgets('present unchecked is never rendered or announced as MATCH',
      (tester) async {
    final semantics = tester.ensureSemantics();
    final harness =
        await readyViewHarness(projection: viewProjection(shape: 'unchecked'));
    await tester.pumpWidget(journeyApp(harness));
    await reveal(tester, find.text('present unchecked'));
    expect(find.text('present unchecked'), findsOneWidget);
    expect(find.text('MATCH'), findsNothing);
    expect(find.bySemanticsLabel(RegExp('MATCH', caseSensitive: false)),
        findsNothing);
    semantics.dispose();
  });
}

void _nullAndExtensionTests() {
  testWidgets('extension host contributes no content semantics or extent',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: const Center(child: JourneyExtensionHost(lens: JourneyLens.verify)),
    ));
    expect(tester.getSize(find.byType(JourneyExtensionHost)), Size.zero);
    expect(
        find.descendant(
            of: find.byType(JourneyExtensionHost),
            matching: find.byType(Semantics)),
        findsNothing);
    expect(find.byType(Text), findsNothing);
  });
}
