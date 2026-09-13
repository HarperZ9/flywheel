import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/process_audit_review.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/process_audit_review_result_view.dart';

const _hashA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _hashB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _hashC =
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';
const _hashD =
    'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  test('review result rejects cross-field inconsistent gateway verdicts', () {
    final upload = _upload();

    final internalDrift = _mutatedReview(upload, (body) {
      final verification = body['verification']! as Map<String, Object?>;
      final gateway = body['gateway_effect_verification']! as Map;
      (gateway['internal_consistency']! as Map)['verdict'] = 'DRIFT';
      verification['packet_local_verdict'] = 'MATCH';
      verification['gateway_effect_verdict'] = 'MATCH';
    });
    final expectedDriftButOverallMatch = _mutatedReview(upload, (body) {
      final gateway =
          body['gateway_effect_verification']! as Map<String, Object?>;
      final expected =
          gateway['expected_correspondence']! as Map<String, Object?>;
      final check = (expected['checks']! as List).single as Map;
      expected['verdict'] = 'DRIFT';
      check['verdict'] = 'DRIFT';
      check['expected_sha256'] = _hashA;
      gateway['verdict'] = 'MATCH';
      (body['verification']! as Map<String, Object?>)['verdict'] = 'MATCH';
    });
    final localDriftButOverallMatch = _mutatedReview(upload, (body) {
      body['assessment'] = 'packet-local-drift';
      final verification = body['verification']! as Map<String, Object?>;
      verification['packet_local_verdict'] = 'DRIFT';
      verification['verdict'] = 'MATCH';
    });

    for (final body in [
      internalDrift,
      expectedDriftButOverallMatch,
      localDriftButOverallMatch,
    ]) {
      expect(
        ProcessAuditReviewResult.fromJson(body, upload).errorCode,
        'INVALID_RESPONSE',
      );
    }
  });

  test('wrapper packet pointers resolve to nested packet source bytes', () {
    final upload = _upload();

    final result =
        ProcessAuditReviewResult.fromJson(_reviewBody(upload), upload);
    final sourceValue = result.sourcePointers
        .singleWhere((item) => item.pointer == '/source_values/target_state');

    expect(result.errorCode, isNull);
    expect(sourceValue.location?.pointer, '/packet/source_values/target_state');
    expect(sourceValue.location?.context, '"closed"');
  });

  testWidgets('derived preview points at trace records and renders limits',
      (tester) async {
    final upload = _upload();
    final result =
        ProcessAuditReviewResult.fromJson(_reviewBody(upload), upload);
    final derived = result.sourcePointers
        .singleWhere((item) => item.pointer == '/gateway_effect/trace_preview');

    expect(derived.source, 'derived_from_submitted_trace_records');
    expect(derived.privacy, 'content_free_preview');
    expect(derived.limits.single,
        'full trace_records are private exact-review input');
    expect(derived.location?.pointer, '/packet/gateway_effect/trace_records');
    expect(derived.location?.context, contains('private record exact input'));
    expect(derived.location?.context, isNot(contains('forged-preview')));

    await tester
        .pumpWidget(_wrap(ProcessAuditReviewResultView(result: result)));
    expect(find.textContaining('DERIVED'), findsOneWidget);
    expect(find.textContaining('content_free_preview'), findsOneWidget);
    expect(
      find.textContaining('full trace_records are private exact-review input'),
      findsOneWidget,
    );
    expect(find.text('/gateway_effect/trace_preview'), findsOneWidget);

    final pointer = find.text('/gateway_effect/trace_preview');
    await tester.ensureVisible(pointer);
    await tester.tap(pointer);
    await tester.pumpAndSettle();
    expect(find.textContaining('private record exact input'), findsNothing);
    expect(find.text('Show private source context'), findsOneWidget);

    final reveal = find.text('Show private source context');
    await tester.ensureVisible(reveal);
    await tester.tap(reveal);
    await tester.pumpAndSettle();
    expect(find.text('PRIVATE SOURCE CONTEXT'), findsOneWidget);
    expect(find.textContaining('private record exact input'), findsOneWidget);
  });
}

ProcessAuditPacketUpload _upload() => ProcessAuditPacketUpload.fromPickedBytes(
      Uint8List.fromList(utf8.encode(_reviewRequestJson())),
    );

Map<String, Object?> _mutatedReview(ProcessAuditPacketUpload upload,
    void Function(Map<String, Object?> body) mutate) {
  final body =
      jsonDecode(jsonEncode(_reviewBody(upload))) as Map<String, Object?>;
  mutate(body);
  return body;
}

String _reviewRequestJson() => jsonEncode({
      'schema': processAuditReviewRequestSchema,
      'packet': {
        'schema': processAuditPacketSchema,
        'source_values': {'target_state': 'closed'},
        'gateway_effect': {
          'trace_preview': {'record_count': 999, 'note': 'forged-preview'},
          'trace_records': [
            {
              'kind': 'ledger',
              'payload': {'content': 'private record exact input'},
            },
          ],
        },
      },
      'expected_hashes': {'trace_records_sha256': _hashD},
    });

Map<String, Object?> _reviewBody(ProcessAuditPacketUpload upload) => {
      'schema': ProcessAuditReviewResult.schemaName,
      'source': {
        'format': 'incident-sim-process-audit-review-request-json',
        'sha256': upload.sha256,
        'byte_length': upload.byteLength,
      },
      'assessment': 'packet-local-match',
      'semantic_verification': 'UNVERIFIABLE',
      'verification': _verification(),
      'gateway_effect_verification': _gatewayEffect(),
      'declared_access': {'verdict': 'NOT_ASSESSED'},
      'source_pointers': [
        {
          'json_pointer': '/source_values/target_state',
          'source_value': 'closed',
        },
        {
          'json_pointer': '/gateway_effect/trace_preview',
          'source': 'derived_from_submitted_trace_records',
          'privacy': 'content_free_preview',
          'source_value': {
            'record_count': 1,
            'sensitive_payload_categories': ['PRIVATE_TEXT'],
          },
          'limits': ['full trace_records are private exact-review input'],
        },
      ],
      'does_not_prove': const [],
    };

Map<String, Object?> _verification() => {
      'schema': 'flywheel.incident-sim-process-audit-verification/v1',
      'verdict': 'MATCH',
      'packet_local_verdict': 'MATCH',
      'institutional_access_verdict': 'NOT_ASSESSED',
      'packet_digest_verdict': 'MATCH',
      'evaluation_digest_verdict': 'MATCH',
      'source_values_digest_verdict': 'MATCH',
      'independence_digest_verdict': 'MATCH',
      'action_chain_verdict': 'MATCH',
      'work_receipt_verdict': 'MATCH',
      'audit_verdict': 'MATCH',
      'audit_subject_verdict': 'MATCH',
      'receipt_verification_verdict': 'MATCH',
      'gateway_effect_verdict': 'MATCH',
    };

Map<String, Object?> _gatewayEffect() => {
      'schema': 'flywheel.gateway-effect-offline-verification/v1',
      'verdict': 'MATCH',
      'source_sha256': {
        'terminal_result': _hashB,
        'lifecycle_history': _hashC,
        'trace_records': _hashD,
      },
      'internal_consistency': {'verdict': 'MATCH'},
      'expected_correspondence': {
        'verdict': 'MATCH',
        'reference_provenance': 'reviewer fixture',
        'checks': [
          {
            'artifact': 'trace_records',
            'expected_sha256': _hashD,
            'computed_sha256': _hashD,
            'verdict': 'MATCH',
          },
        ],
        'limits': const [],
      },
      'effect_coverage': {
        'verdict': 'MATCH',
        'retained_observations': 0,
        'omitted_observations': 0,
        'known_observations_digest': _hashA,
        'known_observations': const [],
        'action_witness': {'status': 'absent'},
        'tool_call_receipts': {'status': 'absent'},
        'unobserved_scope': const [],
        'trace_head_sha256': _hashD,
      },
      'semantic_correctness': {
        'verdict': 'UNVERIFIABLE',
        'does_not_verify': ['semantic correctness'],
      },
    };
