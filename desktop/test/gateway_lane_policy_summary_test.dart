// A lane.call proposal summary carries the engine's lane_policy block (the
// tier, effect and plain arguments the owner approves). The summary model
// accepts it for lane.call only, and the approval sheet renders it (WP9b).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:flywheel_desktop/widgets/lane_policy_review.dart';

const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

Map<String, Object?> _summary(String action, {Object? lanePolicy}) => {
      'schema': 'flywheel.gateway-grant-summary/v1',
      'action': action,
      'journey_ref': _journey,
      'expected_event_head': _head,
      'destination': {'kind': 'lane', 'ref': 'relay'},
      'tool': action == 'lane.call' ? 'local_agent_run' : action,
      'operation_sha256': _head,
      'arguments_sha256': _head,
      'scopes': ['exec', 'network', 'plugin'],
      'data_refs': <String>[],
      'credential_refs': <String>[],
      'effect': 'one dispatch after approval',
      'expires_at': '2026-08-15T12:02:00Z',
      if (lanePolicy != null) 'lane_policy': lanePolicy,
    };

void main() {
  const review = {
    'required_tier': 'T1',
    'requested_tier': 'T1',
    't2': false,
    'arguments': {'goal': 'g', 'allow_exec': false},
    'dropped_arguments': ['check'],
  };

  test('a lane.call summary keeps its lane policy block', () {
    final summary =
        GatewayGrantSummary.fromJson(_summary('lane.call', lanePolicy: review));
    expect(summary.invalidResponse, isFalse);
    expect(summary.lanePolicy?['required_tier'], 'T1');
    expect(summary.lanePolicy?['dropped_arguments'], ['check']);
  });

  test('a lane policy block on another action, or not an object, is refused',
      () {
    expect(
        GatewayGrantSummary.fromJson(
                _summary('plugin.probe', lanePolicy: review))
            .invalidResponse,
        isTrue);
    expect(
        GatewayGrantSummary.fromJson(_summary('lane.call', lanePolicy: 'T2'))
            .invalidResponse,
        isTrue);
  });

  test('the sheet lines state tier, forced and dropped arguments', () {
    final lines = lanePolicyLines(const {
      'required_tier': 'T1',
      'requested_tier': 'T1',
      'effect': 'model_call',
      'forced_arguments': {'allow_exec': false},
      'dropped_arguments': ['check'],
      'arguments': {'goal': 'g', 'allow_exec': false},
    });
    expect(lines, [
      'Tier: needs T1, asks T1',
      'Effect: model_call',
      'Engine sets: {"allow_exec":false}',
      'Engine drops: check',
      'Lane receives: {"goal":"g","allow_exec":false}',
    ]);
  });

  testWidgets('the approval sheet block renders every line', (tester) async {
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: LanePolicyReview(policy: review))));
    expect(find.text('Lane tool policy'), findsOneWidget);
    expect(find.text('Engine drops: check'), findsOneWidget);
  });

  test('a lane.call summary without the block still parses', () {
    final summary = GatewayGrantSummary.fromJson(_summary('lane.call'));
    expect(summary.invalidResponse, isFalse);
    expect(summary.lanePolicy, isNull);
  });
}
