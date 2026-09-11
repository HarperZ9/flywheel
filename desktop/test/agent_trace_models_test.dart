import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/agent_trace.dart';
import 'package:flywheel_desktop/models/agent_trace_record.dart';
import 'package:flywheel_desktop/models/agent_trace_json.dart';

const operation = 'op_cccccccccccccccccccccccccccccccc';
const journey = 'jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const trace = 'agt_3e2197a3f63109a97f701d387b758689';
Map<String, dynamic> fixture(String name) =>
    jsonDecode(File('../tests/fixtures/native_agent_trace/$name.json')
        .readAsStringSync()) as Map<String, dynamic>;

TracePage page(Map<String, dynamic> value, {int sequence = 0}) =>
    TracePage.fromJson(value,
        operationRef: operation,
        journeyRef: journey,
        traceRef: trace,
        sequence: sequence);

void main() {
  test(
      'flat JSON allocation and base64 padding boundaries report reader limits',
      () {
    for (final raw in ['{"a":[0,0,0,0]}', '{"a":0,"b":0,"c":0,"d":0}']) {
      expect(() => traceJsonObject(utf8.encode(raw), maxNodes: 4),
          throwsA(isA<TraceLimitException>()));
    }
    // 8 MiB + 1 shares the accepted base64 character count due to padding.
    final detail = fixture('detail')
      ..['record_canonical_base64'] =
          base64Encode(List.filled(traceMaxRecordBytes + 1, 32));
    expect(() => page(detail), throwsA(isA<TraceLimitException>()));
  });
  test('private JSON preserves Python large integers without rounding', () {
    final value =
        traceJsonObject(utf8.encode('{"large":9223372036854775809,"small":2}'));
    expect(value['large'], BigInt.parse('9223372036854775809'));
    expect(value['small'], 2);
    final detail = fixture('detail');
    final original = Map<String, dynamic>.from(detail['record'])
      ..remove('record_sha256');
    final raw =
        jsonEncode(original).replaceFirst('1.25', '9223372036854775809');
    final bytes = utf8.encode(raw);
    detail['record_canonical_base64'] = base64Encode(bytes);
    detail['record'] = {
      ...traceJsonObject(bytes),
      'record_sha256': sha256.convert(bytes).toString()
    };
    expect(page(detail).record.payload['duration_s'],
        BigInt.parse('9223372036854775809'));
    (detail['record'] as Map)['payload']['duration_s'] =
        BigInt.parse('9223372036854775810');
    expect(() => page(detail), throwsFormatException);
  });
  test('backend projections retain explicit omissions and distinct states', () {
    for (final state in ['running', 'completed', 'failed', 'cancelled']) {
      final projection = TraceProjection.fromJson(fixture(state),
          operationRef: operation, journeyRef: journey);
      expect(projection.state, state);
      expect(projection.recordCount, 3);
      expect(projection.omissions, contains('PRIVATE_CONTENT'));
      expect(projection.doesNotProve, contains('NOT_SEMANTIC_TRUTH'));
      expect(() => projection.omissions.add('new'), throwsUnsupportedError);
    }
  });

  test('projection tampering, cross operation and extra content are refused',
      () {
    for (final patch in [
      {'record_count': 2049},
      {'state': 'verified'},
      {'trace_head_sha256': 'x'},
      {'final': 'private content'},
      {'projection_sha256': '0' * 64},
      {'operation_ref': 'op_${'a' * 32}'},
      {'journey_ref': 'jrn_${'a' * 32}'},
    ]) {
      expect(
          () => TraceProjection.fromJson({...fixture('completed'), ...patch},
              operationRef: operation, journeyRef: journey),
          throwsFormatException);
    }
  });

  test('private record hashes exact backend bytes including floats and Unicode',
      () {
    final detail = page(fixture('detail'));
    expect(detail.record.payload['duration_s'], 1.25);
    expect(detail.record.payload['usage_cost'], 0.001);
    expect(detail.record.payload['final'], contains('café'));
    expect(detail.record.canonicalText, contains('naïve ✓'));
    expect(detail.record.ownerRef, 'owner_${'a' * 32}');
    expect(detail.nextSequence, isNull);
    expect(() => detail.record.payload['new'] = true, throwsUnsupportedError);
  });

  test('canonical bytes and returned record must agree, not just self hash',
      () {
    final changed = fixture('detail');
    (changed['record'] as Map)['payload']['final'] = 'substituted';
    expect(() => page(changed), throwsFormatException);
    final hashChanged = fixture('detail');
    (hashChanged['record'] as Map)['record_sha256'] = 'f' * 64;
    expect(() => page(hashChanged), throwsFormatException);
    final ownerChanged = fixture('detail');
    final body = Map<String, dynamic>.from(ownerChanged['record'] as Map)
      ..remove('record_sha256')
      ..['owner_ref'] = 'owner_${'b' * 32}';
    final bytes = utf8.encode(jsonEncode(body));
    ownerChanged['record_canonical_base64'] = base64Encode(bytes);
    ownerChanged['record'] = {
      ...body,
      'record_sha256': sha256.convert(bytes).toString()
    };
    expect(() => page(ownerChanged), throwsFormatException);
  });

  test('binding, sequence and next-page mismatches never become records', () {
    for (final patch in [
      {'operation_ref': 'op_${'a' * 32}'},
      {'journey_ref': 'jrn_${'a' * 32}'},
      {'trace_ref': 'agt_${'a' * 32}'},
      {'record_count': 0},
      {'next_sequence': 0},
      {'next_sequence': 1},
    ]) {
      expect(
          () => page({...fixture('detail'), ...patch}), throwsFormatException);
    }
    expect(() => page(fixture('detail'), sequence: 1), throwsFormatException);
  });

  test(
      'private JSON rejects duplicates, invalid scalars, depth and byte excess',
      () {
    for (final raw in [
      '{"a":1,"a":2}',
      '{"a":"\\ud800"}',
      '{"a":1e999}',
      '{"a":NaN}',
      '{"a":${'[' * 40}0${']' * 40}}',
    ]) {
      expect(() => traceJsonObject(utf8.encode(raw)), throwsFormatException);
    }
    expect(() => traceJsonObject(utf8.encode('{"a":1}'), maxBytes: 2),
        throwsFormatException);
    expect(traceJsonObject(utf8.encode('{"a":{}}'), maxDepth: 2), {'a': {}});
    expect(() => traceJsonObject(utf8.encode('{"a":{"b":{}}}'), maxDepth: 2),
        throwsFormatException);
  });
}
