// lane_status_truth_test.dart - the Tools view says what the engine says.
//
// D1: a probed row stays on screen until a newer probe replaces it; the 5 s
// status poll used to overwrite it with the unprobed read. D2 and D9: the
// headline and the counts come from each row's `state`, never from the
// presence status, and an unprobed lane never reads "unverified". H-2: a
// health answer alone never produces a "Runs" or "Ready" sentence. H-10: a
// row checked by an earlier engine session reads "Last checked <time>".

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/models/lane_readiness.dart';
import 'package:flywheel_desktop/models/lane_state.dart';
import 'package:flywheel_desktop/shell/gateway_status_coordinator.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/lanes_view.dart';

const _t1 = '2026-09-26T10:00:00Z';
const _t2 = '2026-09-26T10:05:00Z';

Map<String, dynamic> _row(String name, String state,
        {String sentence = '',
        String second = '',
        String? checked = _t1,
        bool fresh = true,
        String code = '',
        String status = 'declared',
        int? tools,
        List<Map<String, dynamic>> setup = const []}) =>
    {
      'name': name,
      'kind': 'bundled',
      'expected_version': '1.0.0',
      'status': status,
      'organ': 'perception',
      'role': 'research intake',
      'detail': tools == null ? 'not MCP-probed' : '$tools tools answered',
      if (tools != null) 'tools': tools,
      'state': state,
      'sentence': sentence,
      'second_line': second,
      'last_checked': checked,
      'checked_this_session': fresh,
      'code': code,
      'setup': setup,
      'main_action': 'catalog a local document',
      'main_tools': ['gather.docs'],
    };

Map<String, dynamic> _roster(List<Map<String, dynamic>> rows) => {
      'n_lanes': rows.length,
      'by_status': {'declared': rows.length},
      'by_state': {'ready': rows.length},
      'lanes': rows,
    };

GatewayStatusCoordinator _coordinator(
    Map<String, dynamic> Function(Uri url, String method) answer,
    {List<String>? contentTypes}) {
  final client = GatewayClient(httpClient: MockClient((r) async {
    if (r.method == 'POST') contentTypes?.add(r.headers['Content-Type'] ?? '');
    return http.Response(jsonEncode(answer(r.url, r.method)), 200);
  }));
  return GatewayStatusCoordinator(
      client: client, status: null, startEngine: () async => null);
}

Future<void> _pumpCard(WidgetTester tester, Map<String, dynamic> row,
    {void Function(String)? onCheck}) {
  return tester.pumpWidget(MaterialApp(
    theme: flywheelLightTheme(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: LaneCard(lane: Lane.fromJson(row), onCheck: onCheck),
      ),
    ),
  ));
}

void main() {
  group('D1: a probed row survives the status poll', () {
    test('the unprobed read of the same probe keeps the probe facts',
        () async {
      final c = _coordinator((url, _) => url.query.contains('probe=true')
          ? _roster([
              _row('gather', 'ready',
                  sentence: 'Ready to catalog.', status: 'live', tools: 8)
            ])
          : _roster([_row('gather', 'ready', sentence: 'Ready to catalog.')]));
      addTearDown(c.dispose);
      await c.probeLanes();
      await c.poll(); // what the 5 s timer does
      final lane = c.roster!.lanes.single;
      expect(lane.state, 'ready');
      expect(lane.status, 'live');
      expect(lane.tools, 8);
    });

    test('a read that lost the probe keeps the row as last checked',
        () async {
      var probed = false;
      final c = _coordinator((url, _) {
        if (url.query.contains('probe=true')) {
          probed = true;
          return _roster([
            _row('gather', 'ready', sentence: 'Ready to catalog.', tools: 8)
          ]);
        }
        return _roster([
          _row('gather', 'not_checked',
              sentence: 'Not checked yet.', checked: null, fresh: false)
        ]);
      });
      addTearDown(c.dispose);
      await c.probeLanes();
      expect(probed, isTrue);
      await c.poll();
      final lane = c.roster!.lanes.single;
      expect(lane.state, 'ready');
      expect(lane.checkedThisSession, isFalse);
      expect(laneCheckedLine(lane), startsWith('Last checked '));
    });

    test('a newer probe replaces the kept row', () async {
      var reads = 0;
      final c = _coordinator((url, _) {
        reads++;
        if (url.query.contains('probe=true')) {
          return _roster([_row('gather', 'ready', tools: 8)]);
        }
        return _roster([
          _row('gather', 'cannot_launch',
              sentence: 'Could not start: lane_cannot_launch.',
              checked: _t2,
              code: 'lane_cannot_launch')
        ]);
      });
      addTearDown(c.dispose);
      await c.probeLanes();
      await c.poll();
      expect(reads, greaterThan(1));
      final lane = c.roster!.lanes.single;
      expect(lane.state, 'cannot_launch');
      expect(lane.tools, isNull);
    });

    test('Check probes one lane and replaces only its row', () async {
      final seen = <String>[];
      // A private POST without a JSON content type is refused with 401.
      final types = <String>[];
      final c = _coordinator(contentTypes: types, (url, method) {
        seen.add('$method ${url.path}');
        if (url.path == '/api/lanes/crucible/check') {
          return _row('crucible', 'ready',
              sentence: 'Ready to check a thesis.', checked: _t2, tools: 13);
        }
        return _roster([
          _row('gather', 'ready', sentence: 'Ready to catalog.'),
          _row('crucible', 'not_checked', checked: null, fresh: false),
        ]);
      });
      addTearDown(c.dispose);
      await c.poll();
      await c.checkLane('crucible');
      expect(seen, contains('POST /api/lanes/crucible/check'));
      expect(types.single, startsWith('application/json'));
      final byName = {for (final l in c.roster!.lanes) l.name: l};
      expect(byName['crucible']!.state, 'ready');
      expect(byName['crucible']!.tools, 13);
      expect(byName['gather']!.state, 'ready');
      expect(c.message, '2 of 2 lanes ready');
    });
  });

  group('D2 and D9: counts and the headline come from state', () {
    test('an unprobed roster reads not checked, never unverified', () {
      final roster = LaneRoster.fromJson(_roster([
        _row('gather', 'not_checked', checked: null),
        _row('crucible', 'not_checked', checked: null),
      ]));
      final line = laneRosterDetail(roster);
      expect(line, '2 not checked');
      expect(line, isNot(contains('unverified')));
    });

    test('counts follow state, and a held lane is not a defect', () {
      final roster = LaneRoster.fromJson(_roster([
        _row('gather', 'ready', status: 'live'),
        _row('index', 'limited', status: 'live'),
        _row('canon', 'needs_setup', status: 'live'),
        _row('local-model', 'needs_setup'),
        _row('calibrate-pro', 'reads_only'),
        _row('telos', 'cannot_launch', code: 'lane_held'),
        _row('forum', 'cannot_launch', code: 'launch_failed'),
        _row('bulletin', 'unreachable'),
        _row('chorus', 'not_checked', checked: null),
      ]));
      expect(laneStateCounts(roster.lanes), {
        'ready': 1,
        'limited': 1,
        'reads_only': 1,
        'needs_setup': 2,
        'not_checked': 1,
        'unreachable': 1,
        'cannot_launch': 1,
        'not_in_build': 1,
      });
      expect(
          laneRosterDetail(roster),
          '1 ready · 1 limited · 1 reads only · 2 need setup · '
          '1 not checked · 1 unreachable · 1 cannot start · '
          '1 not in this build');
    });

    test('an engine with no state keeps the presence wording', () {
      final roster = LaneRoster.fromJson({
        'n_lanes': 2,
        'by_status': {'declared': 2},
        'lanes': [
          {'name': 'gather', 'status': 'declared'},
          {'name': 'crucible', 'status': 'declared'},
        ],
      });
      expect(laneRosterDetail(roster), '2 not probed');
    });
  });

  group('the card, one case per state', () {
    final cases = <String, (Map<String, dynamic>, String, String)>{
      'ready': (
        _row('gather', 'ready', sentence: 'Ready to catalog a document.'),
        'READY',
        'Ready to catalog a document.'
      ),
      'limited': (
        _row('index', 'limited',
            sentence: 'Ready to find symbols. To map a repo, set up: Git.'),
        'LIMITED',
        'Ready to find symbols. To map a repo, set up: Git.'
      ),
      'needs_setup': (
        _row('canon', 'needs_setup',
            sentence: 'Add a context block.',
            second: 'Answers its health check.'),
        'NEEDS SETUP',
        'Add a context block.'
      ),
      'reads_only': (
        _row('calibrate-pro', 'reads_only',
            sentence: 'Reads panel profiles. Calibration runs in the app.'),
        'READS ONLY',
        'Reads panel profiles. Calibration runs in the app.'
      ),
      'cannot_launch': (
        _row('forum', 'cannot_launch',
            sentence: 'Could not start: launch_failed.', code: 'launch_failed'),
        'CANNOT START',
        'Could not start: launch_failed.'
      ),
      'held': (
        _row('telos', 'cannot_launch',
            sentence: 'Not in this build.', code: 'lane_held'),
        'NOT IN BUILD',
        'Not in this build.'
      ),
      'unreachable': (
        _row('bulletin', 'unreachable',
            sentence: 'Cannot reach https://board.example.'),
        'UNREACHABLE',
        'Cannot reach https://board.example.'
      ),
      'not_checked': (
        _row('chorus', 'not_checked', checked: null, fresh: false),
        'NOT CHECKED',
        'Not checked yet.'
      ),
    };
    for (final entry in cases.entries) {
      testWidgets('${entry.key} shows its pill and its sentence',
          (tester) async {
        final (row, pill, sentence) = entry.value;
        await _pumpCard(tester, row);
        expect(find.text(pill), findsOneWidget);
        expect(find.text(sentence), findsOneWidget);
      });
    }

  });
}
