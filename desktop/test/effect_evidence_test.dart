import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/agent_trace.dart';
import 'package:flywheel_desktop/models/agent_trace_record.dart';
import 'package:flywheel_desktop/models/canonical_json.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/agent_trace_viewer.dart';

import 'agent_trace_models_test.dart' show operation, journey, trace;
import 'agent_trace_reader_test.dart' show FakeTraceReader;
import 'effect_evidence_fixtures.dart'
    show effectDetail, witnessDetail, witnessProjection;

const _effectFixture =
    '../tests/fixtures/gateway_effect_evidence/cancelled_projection.json';

Map<String, dynamic> _fixture() =>
    jsonDecode(File(_effectFixture).readAsStringSync())
        as Map<String, dynamic>;

Map<String, dynamic> _copy(Map<String, dynamic> value) =>
    jsonDecode(jsonEncode(value)) as Map<String, dynamic>;

Map<String, dynamic> _rehash(Map<String, dynamic> value) {
  final material = _copy(value)..remove('projection_sha256');
  return {...material, 'projection_sha256': canonicalJsonSha256(material)};
}

TraceProjection _projection([Map<String, dynamic>? value]) =>
    TraceProjection.fromJson(value ?? _fixture(),
        operationRef: operation, journeyRef: journey);

void _expectRejected(Map<String, dynamic> value) {
  expect(() => _projection(value), throwsFormatException);
}

void main() {
  test('Python-produced effect evidence fixture parses with bounded descriptors',
      () {
    final dynamic projection = _projection();
    final evidence = projection.effectEvidence;
    expect(projection.state, 'cancelled');
    expect(evidence.knownObservationCount, 1);
    expect(evidence.knownObservationsOmitted, 0);
    expect(evidence.basis.terminalBasisEventType, 'cancel_requested');
    expect(evidence.unknownEffectScope,
        contains('NOT_CURRENT_FILESYSTEM_STATE'));
    expect(evidence.knownObservations.single.jsonPointer,
        '/payload/meta/edited');
    expect(evidence.knownObservations.single.valueSha256,
        'c4eeaad21bc73469ce758d39a74aa854141fcd93497f4eaf0747bf27de7b007f');
    final rawEvidence = _fixture()['effect_evidence'] as Map<String, dynamic>;
    expect(jsonEncode(rawEvidence['known_observations']),
        isNot(contains('example')));
  });

  test('legacy projections still parse without implying zero effects', () {
    final legacy = jsonDecode(File('../tests/fixtures/native_agent_trace/'
                'cancelled.json')
            .readAsStringSync())
        as Map<String, dynamic>;
    final dynamic projection = _projection(legacy);
    expect(projection.effectEvidence, isNull);
    expect(projection.recordCount, 3);
  });

  test('present effect evidence is refused when malformed or rebound', () {
    final wrongSchema = _copy(_fixture());
    (wrongSchema['effect_evidence'] as Map)['schema'] = 'fake';
    _expectRejected(_rehash(wrongSchema));

    final wrongTrace = _copy(_fixture());
    ((wrongTrace['effect_evidence'] as Map)['basis'] as Map)['trace_ref'] =
        'agt_${'1' * 32}';
    _expectRejected(_rehash(wrongTrace));

    final wrongCount = _copy(_fixture());
    final evidence = wrongCount['effect_evidence'] as Map;
    evidence['known_observation_count'] = 2;
    evidence['known_observations_omitted'] = 0;
    evidence['known_observations_digest'] = 'f' * 64;
    _expectRejected(_rehash(wrongCount));
  });

  test('projection digest still binds optional effect evidence bytes', () {
    final changed = _copy(_fixture());
    (changed['effect_evidence'] as Map)['known_observation_count'] = 0;
    _expectRejected(changed);
  });

  test('omitted descriptors and unavailable witness states remain explicit', () {
    final value = _copy(_fixture());
    value['record_count'] = 65;
    value['trace_head_sha256'] = 'f' * 64;
    final evidence = value['effect_evidence'] as Map;
    final basis = evidence['basis'] as Map;
    basis['record_count'] = 65;
    basis['trace_head_sha256'] = 'f' * 64;
    evidence['known_observation_count'] = 65;
    evidence['known_observations_omitted'] = 1;
    evidence['known_observations'] = List.generate(64, (sequence) {
      final observation =
          Map<String, dynamic>.from((evidence['known_observations'] as List).single);
      observation['trace_sequence'] = sequence;
      observation['record_sha256'] =
          sequence == 64 ? 'f' * 64 : sequence.toRadixString(16).padLeft(64, '0');
      return observation;
    });
    evidence['known_observations_digest'] = 'e' * 64;
    evidence['action_witness'] = {
      'status': 'unavailable',
      'reason': 'UNSUPPORTED_SOURCE_RECORD_KIND',
      'trace_sequence': 0,
      'record_sha256': '0' * 64,
      'record_kind': 'progress',
      'json_pointer': '/payload/action_witness',
    };
    final dynamic projection = _projection(_rehash(value));
    expect(projection.effectEvidence.knownObservationsOmitted, 1);
    expect(projection.effectEvidence.actionWitness.status, 'unavailable');
  });

  test('reported witness and receipt summaries parse as source descriptors', () {
    final fixture = jsonDecode(File('../tests/fixtures/gateway_effect_evidence/'
                'completed_projection_with_reported_witnesses.json')
            .readAsStringSync())
        as Map<String, dynamic>;
    final dynamic projection = _projection(fixture);
    expect(projection.state, 'completed');
    expect(projection.effectEvidence.knownObservationCount, 0);
    expect(projection.effectEvidence.actionWitness.status, 'present');
    expect(projection.effectEvidence.actionWitness.traceSequence, 0);
    expect(projection.effectEvidence.actionWitness.count, 2);
    expect(projection.effectEvidence.toolCallReceipts.status, 'present');
    expect(projection.effectEvidence.toolCallReceipts.count, 3);
  });

  test('reported chain counts do not use the trace-record cap', () {
    final value = jsonDecode(File('../tests/fixtures/gateway_effect_evidence/'
                'completed_projection_with_reported_witnesses.json')
            .readAsStringSync())
        as Map<String, dynamic>;
    final evidence = value['effect_evidence'] as Map;
    (evidence['action_witness'] as Map)['count'] = 2049;
    (evidence['tool_call_receipts'] as Map)['count'] = 2049;

    final dynamic projection = _projection(_rehash(value));
    expect(projection.effectEvidence.actionWitness.count, 2049);
    expect(projection.effectEvidence.toolCallReceipts.count, 2049);

    final badSequence = _copy(value);
    final badAction =
        (badSequence['effect_evidence'] as Map)['action_witness'] as Map;
    badAction['trace_sequence'] = 1;
    _expectRejected(_rehash(badSequence));
  });

  testWidgets('effect source value is shown only after private trace read',
      (tester) async {
    final pending = Completer<TracePage>();
    final reader = FakeTraceReader((p, seq) => pending.future);
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: SingleChildScrollView(
                child: AgentTraceViewer(
                    projection: _projection(), reader: reader)))));

    expect(find.textContaining('1 retained observation'), findsOneWidget);
    expect(find.textContaining('cancel_requested'), findsOneWidget);
    expect(find.textContaining('NOT_CURRENT_FILESYSTEM_STATE'), findsOneWidget);
    expect(find.textContaining('/payload/meta/edited'), findsNothing);
    expect(find.textContaining('example.txt'), findsNothing);

    await tester.tap(find.text('Read private trace'));
    await tester.pump();
    pending.complete(TracePage.fromJson(effectDetail(),
        operationRef: operation,
        journeyRef: journey,
        traceRef: trace,
        sequence: 0));
    await tester.pumpAndSettle();

    expect(find.textContaining('/payload/meta/edited'), findsOneWidget);
    expect(find.textContaining('example.txt'), findsWidgets);
    expect(find.textContaining('source value hash matches'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('reported witness summaries use private source navigation',
      (tester) async {
    final pending = Completer<TracePage>();
    final reader = FakeTraceReader((p, seq) => pending.future);
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: SingleChildScrollView(
                child: AgentTraceViewer(
                    projection: witnessProjection(_projection), reader: reader)))));

    expect(find.textContaining('Witness present; tool receipts present'),
        findsOneWidget);
    expect(find.textContaining('/payload/action_witness'), findsNothing);
    expect(find.textContaining('action detail'), findsNothing);

    await tester.tap(find.text('Read private trace'));
    await tester.pump();
    pending.complete(TracePage.fromJson(witnessDetail(),
        operationRef: operation,
        journeyRef: journey,
        traceRef: trace,
        sequence: 0));
    await tester.pumpAndSettle();

    expect(find.textContaining('/payload/action_witness'), findsOneWidget);
    expect(find.textContaining('/payload/tool_call_receipts'), findsOneWidget);
    expect(find.textContaining('action detail'), findsWidgets);
    expect(find.textContaining('private-receipts'), findsWidgets);
    expect(find.textContaining('source value hash matches'), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });

  testWidgets('large source values are previewed with explicit truncation',
      (tester) async {
    final large = 'x' * 6000;
    final pending = Completer<TracePage>();
    final reader = FakeTraceReader((p, seq) => pending.future);
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: SingleChildScrollView(
                child: AgentTraceViewer(
                    projection: witnessProjection(_projection,
                        actionDetail: large),
                    reader: reader)))));

    await tester.tap(find.text('Read private trace'));
    await tester.pump();
    pending.complete(TracePage.fromJson(witnessDetail(actionDetail: large),
        operationRef: operation,
        journeyRef: journey,
        traceRef: trace,
        sequence: 0));
    await tester.pumpAndSettle();

    expect(find.textContaining('first 4096'), findsOneWidget);
    expect(find.textContaining('full canonical context'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
