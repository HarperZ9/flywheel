import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/agent_trace_reader.dart';
import 'package:flywheel_desktop/controllers/agent_trace_controller.dart';
import 'package:flywheel_desktop/models/agent_trace.dart';
import 'package:flywheel_desktop/models/agent_trace_record.dart';
import 'package:flywheel_desktop/models/canonical_json.dart';
import 'agent_trace_models_test.dart' show fixture, operation, journey;
import 'agent_trace_reader_test.dart' show FakeTraceReader;

// Synthetic pages model two retained original ledger records, never user history.
List<Map<String, dynamic>> chain(
    {bool brokenPrior = false, int textLength = 0}) {
  final pages = <Map<String, dynamic>>[];
  var prior = traceGenesis;
  for (var sequence = 0; sequence < 2; sequence++) {
    final original =
        Map<String, dynamic>.from(fixture('detail')['record'] as Map)
          ..remove('record_sha256')
          ..['sequence'] = sequence
          ..['kind'] = 'ledger'
          ..['prior_sha256'] = brokenPrior && sequence == 1 ? 'a' * 64 : prior
          ..['payload'] = {
            'ledger_jsonl': '{"thread":"synthetic"}\n',
            'source': 'original café ✓${'x' * textLength}'
          };
    final bytes = utf8.encode(jsonEncode(original));
    prior = sha256.convert(bytes).toString();
    pages.add(fixture('detail')
      ..['record'] = {...original, 'record_sha256': prior}
      ..['record_canonical_base64'] = base64Encode(bytes)
      ..['record_count'] = 2
      ..['next_sequence'] = sequence == 0 ? 1 : null);
  }
  for (final page in pages) {
    page['trace_head_sha256'] = prior;
  }
  return pages;
}

TraceProjection chainProjection(List<Map<String, dynamic>> pages,
    {String state = 'completed', int? count}) {
  final material = fixture('detail_projection')..remove('projection_sha256');
  material['record_count'] = count ?? pages.length;
  material['state'] = state;
  material['trace_head_sha256'] =
      (pages[(count ?? pages.length) - 1]['record'] as Map)['record_sha256'];
  return TraceProjection.fromJson(
      {...material, 'projection_sha256': canonicalJsonSha256(material)},
      operationRef: operation, journeyRef: journey);
}

TracePage chainPage(
        Map<String, dynamic> raw, TraceProjection projection, int sequence) =>
    TracePage.fromJson(raw,
        operationRef: operation,
        journeyRef: journey,
        traceRef: projection.traceRef,
        sequence: sequence);

void main() {
  test('linked original ledger pages reach advertised head without text loss',
      () async {
    final pages = chain();
    final state = AgentTraceController(
        FakeTraceReader((p, seq) async => chainPage(pages[seq], p, seq)),
        chainProjection(pages));
    await state.loadNext();
    expect(state.complete, isFalse);
    expect(state.records.single.payload['ledger_jsonl'],
        '{"thread":"synthetic"}\n');
    await state.loadNext();
    expect(state.complete, isTrue);
    expect(state.records.last.payload['source'], 'original café ✓');
    state.dispose();
  });

  test('self-consistent hashes cannot conceal a broken prior link', () async {
    final pages = chain(brokenPrior: true);
    final state = AgentTraceController(
        FakeTraceReader((p, seq) async => chainPage(pages[seq], p, seq)),
        chainProjection(pages));
    await state.loadNext();
    await state.loadNext();
    expect(state.complete, isFalse);
    expect(state.records, hasLength(1));
    expect(state.failure, TraceReadFailure.integrity);
    state.dispose();
  });

  test('running reads bind advertised prefix even if store has advanced',
      () async {
    final pages = chain();
    final calls = <int>[];
    final state = AgentTraceController(FakeTraceReader((p, seq) async {
      calls.add(seq);
      return chainPage(pages[seq], p, seq);
    }), chainProjection(pages, state: 'running', count: 1));
    await state.loadNext();
    await state.loadNext();
    expect(state.complete, isTrue);
    expect(state.projection.isPartialExecution, isTrue);
    expect(calls, [0]);
    state.dispose();
  });
}
