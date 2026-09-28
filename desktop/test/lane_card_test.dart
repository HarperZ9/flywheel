// lane_card_test.dart - the roster card, and the button it must not offer.
//
// The gateway answers `install_lane` for a bundled or an http lane with "no
// install needed". A card that offers Install for one of those runs the call,
// succeeds, changes nothing, and tells the operator the lane was installed.
// bulletin is the live case: it runs on the open web, so its installed_version
// is null forever and the old `installedVersion == null` guard let it through.
//
// The state cases (WP9a): Check on a lane never checked, "Last checked" on a
// row from an earlier engine session, and no "Ready" or "Runs" sentence on a
// row that only answers its health check (H-2, H-10).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/lanes_view.dart';

Lane _lane(String name, String kind, {String? installed}) => Lane.fromJson({
      'name': name,
      'kind': kind,
      'installed_version': installed,
      'expected_version': '0.2.0',
      'status': 'live',
      'organ': 'correspondence',
      'role': 'the open board',
      'detail': 'reachable at its endpoint',
    });

Future<void> _pump(WidgetTester tester, Lane lane) => tester.pumpWidget(
      MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
          body: LaneCard(lane: lane, onCheck: (_) {}),
        ),
      ),
    );

const _t1 = '2026-09-26T10:00:00Z';

Map<String, dynamic> _stateRow(String name, String state,
        {String sentence = '',
        String second = '',
        String? checked = _t1,
        bool fresh = true,
        String status = 'declared',
        int? tools,
        List<Map<String, dynamic>> setup = const []}) =>
    {
      'name': name,
      'kind': 'bundled',
      'status': status,
      if (tools != null) 'tools': tools,
      'state': state,
      'sentence': sentence,
      'second_line': second,
      'last_checked': checked,
      'checked_this_session': fresh,
      'setup': setup,
      'main_action': 'catalog a local document',
    };

Future<void> _pumpRow(WidgetTester tester, Map<String, dynamic> row,
        {void Function(String)? onCheck}) =>
    tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: LaneCard(lane: Lane.fromJson(row), onCheck: onCheck),
        ),
      ),
    ));

Future<void> _expand(WidgetTester tester, String label) async {
  await tester.tap(find.text(label));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a blocked package distribution offers no install', (
    tester,
  ) async {
    await _pump(
      tester,
      Lane.fromJson({
        'name': 'relay',
        'kind': 'pip',
        'package_installable': false,
        'detail': 'Package distribution disabled; use a source checkout.',
      }),
    );
    expect(find.text('Install'), findsNothing);
    await _expand(tester, 'Relay');
    expect(find.textContaining('use a source checkout'), findsOneWidget);
  });

  testWidgets('a pip lane with nothing installed offers no public install', (
    tester,
  ) async {
    await _pump(tester, _lane('mneme', 'pip'));
    expect(find.text('Install'), findsNothing);
  });

  testWidgets('a remote lane never offers an install it cannot run', (
    tester,
  ) async {
    await _pump(tester, _lane('bulletin', 'http'));
    expect(find.text('Install'), findsNothing);
  });

  testWidgets('a bundled lane carries no install either', (tester) async {
    // A bundled lane reports the engine's own version, so it is covered twice
    // over. The kind is the load-bearing half: the version could go null on a
    // read that fails and the button must still stay away.
    await _pump(tester, _lane('flywheel', 'bundled'));
    expect(find.text('Install'), findsNothing);
  });

  testWidgets('an installed pip lane has nothing left to install', (
    tester,
  ) async {
    await _pump(tester, _lane('mneme', 'pip', installed: '0.2.0'));
    expect(find.text('Install'), findsNothing);
  });

  testWidgets('a lane added to the engine renders in its own words', (
    tester,
  ) async {
    // The card falls back to the raw lane name, so a missing identity entry
    // looks like a working card rather than like the gap it is.
    await _pump(tester, _lane('bulletin', 'http'));
    expect(find.text('Bulletin'), findsOneWidget);
    await _expand(tester, 'Bulletin');
    expect(find.textContaining('accounts belong to agents'), findsOneWidget);
  });

  testWidgets('not checked offers Check, which checks that lane',
      (tester) async {
    final checked = <String>[];
    await _pumpRow(
        tester, _stateRow('chorus', 'not_checked', checked: null, fresh: false),
        onCheck: checked.add);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Check'));
    expect(checked, ['chorus']);
  });

  testWidgets('a row from an earlier session reads Last checked',
      (tester) async {
    await _pumpRow(tester, _stateRow('gather', 'ready', fresh: false));
    final local = DateTime.parse(_t1).toLocal();
    expect(find.textContaining('Last checked '), findsOneWidget);
    expect(find.textContaining('${local.year}-'), findsOneWidget);
    expect(find.textContaining(RegExp(r'^Checked ')), findsNothing);
  });

  testWidgets('a row checked in this session reads Checked',
      (tester) async {
    await _pumpRow(tester, _stateRow('gather', 'ready'));
    expect(find.textContaining(RegExp(r'^Checked ')), findsOneWidget);
    expect(find.textContaining('Last checked'), findsNothing);
  });

  testWidgets('a health-only row has no Runs or Ready sentence',
      (tester) async {
    await _pumpRow(
        tester,
        _stateRow('local-model', 'needs_setup',
            status: 'live',
            tools: 9,
            sentence: 'Choose a project folder.',
            second: 'Answers its health check.'));
    expect(find.text('Answers its health check.'), findsOneWidget);
    expect(find.textContaining('Runs'), findsNothing);
    expect(find.textContaining('Ready'), findsNothing);
    await tester.tap(find.text('Local model'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Runs'), findsNothing);
    expect(find.textContaining('Ready'), findsNothing);
  });

  testWidgets('a live row from an engine with no state claims nothing',
      (tester) async {
    await _pumpRow(tester, {
      'name': 'gather',
      'kind': 'pip',
      'status': 'live',
      'tools': 8,
      'detail': 'gather.status answered',
    });
    expect(find.text('UNKNOWN'), findsOneWidget);
    await tester.tap(find.text('Gather'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Ready'), findsNothing);
    expect(find.textContaining('Runs'), findsNothing);
  });

  testWidgets('unmet setup items are named on the open card',
      (tester) async {
    await _pumpRow(
        tester,
        _stateRow('index', 'limited', sentence: 'Ready to find symbols.', setup: [
          {
            'id': 'git',
            'met': false,
            'title': 'Git',
            'copy': 'Install Git for Windows to read branch and history.',
            'facts': {},
          }
        ]));
    await tester.tap(find.text('Index'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Install Git for Windows'), findsOneWidget);
  });
}
