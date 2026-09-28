import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/process_audit_review.dart';
import 'package:flywheel_desktop/services/inspect_file_picker.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/process_audit_review_panel.dart';

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
  test('upload keeps review request bytes for external expected hashes', () {
    final bytes = Uint8List.fromList(utf8.encode(_reviewRequestJson()));

    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      bytes,
      filename: 'offline-review.json',
    );

    expect(upload.detectedFormat, 'process-audit-review-request');
    expect(upload.bytes, bytes);
    expect(upload.filename, 'offline-review.json');
    expect(upload.locationFor('/expected_hashes/trace_records_sha256')?.context,
        '"$_hashA"');
    expect(upload.locationFor('/packet/schema')?.context,
        '"flywheel.incident-sim-process-audit/v1"');
  });

  test('review result separates packet integrity from reference drift', () {
    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      Uint8List.fromList(utf8.encode(_reviewRequestJson())),
    );

    final result = ProcessAuditReviewResult.fromJson(
      _reviewBody(upload, expectedVerdict: 'DRIFT'),
      upload,
    );

    expect(result.errorCode, isNull);
    expect(result.packetIntegrityStatus, 'verified');
    expect(result.verification.verdict, 'DRIFT');
    expect(result.verification.packetLocalVerdict, 'MATCH');
    final gateway = result.gatewayEffect!;
    expect(gateway.internalConsistency.verdict, 'MATCH');
    expect(gateway.expectedCorrespondence.verdict, 'DRIFT');
    expect(gateway.expectedCorrespondence.referenceProvenance,
        'reviewer supplied hash file');
    expect(
        gateway.expectedCorrespondence.checks.single.artifact, 'trace_records');
    expect(gateway.effectCoverage.retainedObservations, 1);
    expect(gateway.effectCoverage.omittedObservations, 0);
    expect(gateway.effectCoverage.knownObservations.single.jsonPointer,
        '/payload/meta/edited');
    expect(
        gateway.effectCoverage.unobservedScope, contains('NOT_EFFECT_ABSENCE'));
    expect(gateway.semanticCorrectness.verdict, 'UNVERIFIABLE');
  });

  test('malformed gateway effect verification fails closed when present', () {
    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      Uint8List.fromList(utf8.encode(_reviewRequestJson())),
    );
    final body =
        jsonDecode(jsonEncode(_reviewBody(upload))) as Map<String, Object?>;
    final gateway = body['gateway_effect_verification'] as Map<String, Object?>;
    final expected = gateway['expected_correspondence'] as Map<String, Object?>;
    final checks = expected['checks'] as List;
    (checks.single as Map<String, Object?>)['expected_sha256'] = 'not-a-sha';

    final result = ProcessAuditReviewResult.fromJson(body, upload);

    expect(result.errorCode, 'INVALID_RESPONSE');
  });

  testWidgets('review panel renders offline gateway evidence dimensions',
      (tester) async {
    final bytes = Uint8List.fromList(utf8.encode(_reviewRequestJson()));
    late List<int> sent;
    final client = GatewayClient(
      httpClient: MockClient((request) async {
        sent = request.bodyBytes;
        final upload = ProcessAuditPacketUpload.fromPickedBytes(bytes);
        return http.Response(jsonEncode(_reviewBody(upload)), 200);
      }),
    );

    await tester.pumpWidget(_wrap(ProcessAuditReviewPanel(
      client: client,
      picker: _Picker(bytes, filename: 'offline-review.json'),
    )));
    await tester.tap(find.text('Select process-audit JSON'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review packet'));
    await tester.pumpAndSettle();

    expect(sent, bytes);
    expect(find.text('OFFLINE GATEWAY EVIDENCE'), findsOneWidget);
    expect(find.text('INTERNAL CONSISTENCY MATCH'), findsOneWidget);
    expect(find.text('REFERENCE CORRESPONDENCE MATCH'), findsOneWidget);
    expect(find.text('EFFECT COVERAGE MATCH'), findsOneWidget);
    expect(find.text('SEMANTIC CORRECTNESS UNVERIFIABLE'), findsOneWidget);
    expect(find.textContaining('1 retained observations, 0 omitted by cap'),
        findsOneWidget);
    expect(find.textContaining('reviewer supplied hash file'), findsOneWidget);
    expect(find.textContaining('/payload/meta/edited'), findsOneWidget);
    expect(find.textContaining('does not verify semantic correctness'),
        findsOneWidget);
  });
}

String _reviewRequestJson() => jsonEncode({
      'schema': 'flywheel.incident-sim-process-audit-review-request/v1',
      'packet': {'schema': processAuditPacketSchema},
      'expected_hashes': {
        'trace_records_sha256': _hashA,
        'reference_provenance': 'reviewer supplied hash file',
      },
    });

Map<String, Object?> _reviewBody(
  ProcessAuditPacketUpload upload, {
  String expectedVerdict = 'MATCH',
}) =>
    {
      'schema': ProcessAuditReviewResult.schemaName,
      'source': {
        'format': 'incident-sim-process-audit-review-request-json',
        'sha256': upload.sha256,
        'byte_length': upload.byteLength,
      },
      'assessment': 'packet-local-match',
      'semantic_verification': 'UNVERIFIABLE',
      'verification': _verification(expectedVerdict),
      'gateway_effect_verification': _gatewayEffect(expectedVerdict),
      'declared_access': {
        'verdict': 'NOT_ASSESSED',
        'coverage_assessment': 'not_assessed',
        'limits': ['institutional_access component absent'],
      },
      'source_pointers': [
        {
          'json_pointer': '/gateway_effect/trace_preview',
          'source_value': {
            'record_count': 3,
            'sensitive_payload_categories': ['EDIT_FINGERPRINTS'],
          },
        },
      ],
      'does_not_prove': ['semantic correctness of the task or trace'],
    };

Map<String, Object?> _verification(String expectedVerdict) => {
      'schema': 'flywheel.incident-sim-process-audit-verification/v1',
      'verdict': expectedVerdict == 'DRIFT' ? 'DRIFT' : 'MATCH',
      'packet_local_verdict': 'MATCH',
      'verification_scope': 'packet-local digests and receipt seals only',
      'verified_fields': const [],
      'unverified_fields': const [],
      'does_not_verify': const [],
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
      'gateway_effect_verification': _gatewayEffect(expectedVerdict),
    };

Map<String, Object?> _gatewayEffect(String expectedVerdict) => {
      'schema': 'flywheel.gateway-effect-offline-verification/v1',
      'verdict': expectedVerdict == 'DRIFT' ? 'DRIFT' : 'MATCH',
      'source_sha256': {
        'terminal_result': _hashB,
        'lifecycle_history': _hashC,
        'trace_records': _hashD,
      },
      'internal_consistency': {
        'verdict': 'MATCH',
        'checks': [
          {
            'field': '/gateway_effect',
            'verdict': 'MATCH',
            'check': 'component_sha256 excludes itself',
          },
        ],
      },
      'expected_correspondence': {
        'verdict': expectedVerdict,
        'reference_provenance': 'reviewer supplied hash file',
        'checks': [
          {
            'artifact': 'trace_records',
            'expected_sha256': expectedVerdict == 'DRIFT' ? _hashA : _hashD,
            'computed_sha256': _hashD,
            'verdict': expectedVerdict,
          },
        ],
        'limits': ['matching expected hashes show correspondence only'],
      },
      'effect_coverage': {
        'verdict': 'MATCH',
        'retained_observations': 1,
        'omitted_observations': 0,
        'known_observations_digest': _hashA,
        'known_observations': [
          {
            'kind': 'tool_result_edit_fingerprint',
            'trace_sequence': 2,
            'record_sha256': _hashB,
            'record_kind': 'ledger',
            'payload_kind': 'tool_result',
            'json_pointer': '/payload/meta/edited',
            'value_sha256': _hashC,
          },
        ],
        'action_witness': {'status': 'absent'},
        'tool_call_receipts': {'status': 'absent'},
        'unobserved_scope': [
          'NOT_ROLLBACK',
          'NOT_EFFECT_ABSENCE',
          'NOT_CURRENT_FILESYSTEM_STATE',
        ],
        'trace_head_sha256': _hashD,
      },
      'semantic_correctness': {
        'verdict': 'UNVERIFIABLE',
        'does_not_verify': ['semantic correctness'],
      },
    };

class _Picker implements InspectFilePicker {
  const _Picker(this.bytes, {this.filename});
  final Uint8List bytes;
  final String? filename;

  @override
  Future<PickedInspectFile?> pick() async =>
      PickedInspectFile(bytes, filename: filename);
}
