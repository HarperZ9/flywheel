import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/process_audit_review.dart';

void main() {
  test('upload detects an outer command report and sends exact audit_packet',
      () {
    const inner = '{\n'
        '  "schema" : "flywheel.incident-sim-process-audit/v1",\n'
        '  "source_values" : {"target_state" : "closed"}\n'
        '}';
    final outer = Uint8List.fromList(utf8.encode(
      '{"schema":"flywheel.incident-sim-command/v1",'
      '"audit_packet":$inner,"tail":1}',
    ));

    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      outer,
      filename: 'command.json',
    );

    expect(upload.detectedFormat, 'outer-command-report');
    expect(utf8.decode(upload.bytes), inner);
    expect(upload.byteLength, utf8.encode(inner).length);
    expect(upload.filename, 'command.json');
    expect(
        upload.locationFor('/source_values/target_state')?.context, '"closed"');
    expect(upload.locationFor('/source_values/target_state')?.line, 3);
  });

  test('upload rejects duplicate keys before JSON maps can collapse them', () {
    const schema = 'flywheel.incident-sim-process-audit/v1';
    final nestedDuplicate = Uint8List.fromList(utf8.encode(
      '{"audit_packet":{"schema":"$schema","schema":"$schema"}}',
    ));
    final wrapperDuplicate = Uint8List.fromList(utf8.encode(
      '{"audit_packet":{"schema":"$schema"},'
      '"audit_packet":{"schema":"$schema"}}',
    ));

    void expectDuplicate(Uint8List bytes) => expect(
          () => ProcessAuditPacketUpload.fromPickedBytes(bytes),
          throwsA(isA<ProcessAuditReviewException>()
              .having((error) => error.code, 'code', 'DUPLICATE_KEYS')),
        );

    expectDuplicate(nestedDuplicate);
    expectDuplicate(wrapperDuplicate);
  });

  test('upload bounds selected bytes before UTF-8 or JSON decoding', () {
    expect(
      () => ProcessAuditPacketUpload.fromPickedBytes(
        Uint8List(maxProcessAuditPacketBytes + 1),
      ),
      throwsA(isA<ProcessAuditReviewException>()
          .having((error) => error.code, 'code', 'PAYLOAD_TOO_LARGE')),
    );
  });

  test('review result separates packet integrity from declared access coverage',
      () {
    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      Uint8List.fromList(utf8.encode(
        '{"schema":"flywheel.incident-sim-process-audit/v1",'
        '"source_values":{"target_state":"closed"}}',
      )),
    );

    final result = ProcessAuditReviewResult.fromJson({
      'schema': ProcessAuditReviewResult.schemaName,
      'source': {
        'format': 'incident-sim-process-audit-json',
        'sha256': upload.sha256,
        'byte_length': upload.byteLength,
      },
      'assessment': 'packet-local-drift',
      'semantic_verification': 'UNVERIFIABLE',
      'verification': {
        'schema': 'flywheel.incident-sim-process-audit-verification/v1',
        'verdict': 'DRIFT',
        'institutional_access_verdict': 'DRIFT',
        'packet_digest_verdict': 'DRIFT',
        'evaluation_digest_verdict': 'MATCH',
        'source_values_digest_verdict': 'MATCH',
        'independence_digest_verdict': 'MATCH',
        'action_chain_verdict': 'MATCH',
        'work_receipt_verdict': 'MATCH',
        'audit_verdict': 'MATCH',
        'audit_subject_verdict': 'MATCH',
        'receipt_verification_verdict': 'MATCH',
      },
      'declared_access': {
        'verdict': 'DRIFT',
        'coverage_assessment': 'unknown',
        'reported_coverage_assessment': 'complete',
        'limits': ['reported coverage is untrusted'],
      },
      'source_pointers': [
        {
          'json_pointer': '/source_values/target_state',
          'source_value': 'closed',
        },
      ],
      'does_not_prove': ['actual lab access'],
    }, upload);

    expect(result.errorCode, isNull);
    expect(result.assessment, 'packet-local-drift');
    expect(result.packetIntegrityStatus, 'drift');
    expect(result.declaredAccess.coverageAssessment, 'unknown');
    expect(result.declaredAccess.reportedCoverageAssessment, 'complete');
    expect(result.sourcePointers.single.location?.offset, isNonNegative);
    expect(result.sourcePointers.single.sourceValueText, 'closed');
  });

  test('review result accepts backend drift with a matching packet digest', () {
    final fixture = _fixture('process_audit_resealed_component_review.json');
    final raw = fixture['packet_json']! as String;
    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      Uint8List.fromList(utf8.encode(raw)),
    );
    final review = Map<String, Object?>.from(fixture['review']! as Map);

    final result = ProcessAuditReviewResult.fromJson(review, upload);

    expect(result.errorCode, isNull);
    expect(result.packetIntegrityStatus, 'drift');
    expect(result.verification.verdict, 'DRIFT');
    expect(result.verification.packetDigest, 'MATCH');
    expect(result.verification.evaluationDigest, 'DRIFT');
    expect(result.verification.auditSubject, 'DRIFT');
  });

  test('review result accepts backend drift carried only by verified fields',
      () {
    final fixture = _fixture('process_audit_resealed_incident_review.json');
    final raw = fixture['packet_json']! as String;
    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      Uint8List.fromList(utf8.encode(raw)),
    );
    final review = Map<String, Object?>.from(fixture['review']! as Map);

    final result = ProcessAuditReviewResult.fromJson(review, upload);

    expect(result.errorCode, isNull);
    expect(result.verification.verdict, 'DRIFT');
    expect(result.verification.packetDigest, 'MATCH');
    expect(result.verification.independenceDigest, 'MATCH');
    expect(result.verification.failedFields.single.field, '/incident');
    expect(result.verification.failedFields.single.check,
        'canonical_sha256 matches /section_sha256');
  });

  test('review result rejects malformed overall and access coverage promotion',
      () {
    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      Uint8List.fromList(utf8.encode(
        '{"schema":"flywheel.incident-sim-process-audit/v1"}',
      )),
    );
    final matchWithDrift = _reviewBody(upload, actionChain: 'DRIFT');
    final matchWithVerifiedDrift = _reviewBody(upload, verifiedFields: [
      {
        'field': '/incident',
        'verdict': 'DRIFT',
        'check': 'canonical_sha256 matches /section_sha256',
      },
    ]);
    final completeDriftAccess = _reviewBody(
      upload,
      assessment: 'packet-local-drift',
      verdict: 'DRIFT',
      accessVerdict: 'DRIFT',
      declaredAccess: {
        'verdict': 'DRIFT',
        'coverage_assessment': 'complete',
        'reported_coverage_assessment': 'complete',
        'limits': ['reported coverage is untrusted'],
      },
    );

    expect(
      ProcessAuditReviewResult.fromJson(matchWithDrift, upload).errorCode,
      'INVALID_RESPONSE',
    );
    expect(
      ProcessAuditReviewResult.fromJson(matchWithVerifiedDrift, upload)
          .errorCode,
      'INVALID_RESPONSE',
    );
    expect(
      ProcessAuditReviewResult.fromJson(completeDriftAccess, upload).errorCode,
      'INVALID_RESPONSE',
    );
  });

  test('review result rejects missing or inconsistent verification', () {
    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      Uint8List.fromList(utf8.encode(
        '{"schema":"flywheel.incident-sim-process-audit/v1"}',
      )),
    );
    final missing = _reviewBody(upload)..remove('verification');
    final inconsistent = _reviewBody(upload, assessment: 'packet-local-drift');

    expect(
      ProcessAuditReviewResult.fromJson(missing, upload).errorCode,
      'INVALID_RESPONSE',
    );
    expect(
      ProcessAuditReviewResult.fromJson(inconsistent, upload).errorCode,
      'INVALID_RESPONSE',
    );
  });
}

Map<String, Object?> _reviewBody(
  ProcessAuditPacketUpload upload, {
  String assessment = 'packet-local-match',
  String verdict = 'MATCH',
  String accessVerdict = 'NOT_ASSESSED',
  String packetDigest = 'MATCH',
  String evaluationDigest = 'MATCH',
  String sourceValuesDigest = 'MATCH',
  String independenceDigest = 'MATCH',
  String actionChain = 'MATCH',
  String workReceipt = 'MATCH',
  String audit = 'MATCH',
  String auditSubject = 'MATCH',
  String receiptVerification = 'MATCH',
  Map<String, Object?>? declaredAccess,
  List<Map<String, Object?>>? verifiedFields,
}) =>
    {
      'schema': ProcessAuditReviewResult.schemaName,
      'source': {
        'format': 'incident-sim-process-audit-json',
        'sha256': upload.sha256,
        'byte_length': upload.byteLength,
      },
      'assessment': assessment,
      'verification': {
        'verdict': verdict,
        'institutional_access_verdict': accessVerdict,
        'packet_digest_verdict': packetDigest,
        'evaluation_digest_verdict': evaluationDigest,
        'source_values_digest_verdict': sourceValuesDigest,
        'independence_digest_verdict': independenceDigest,
        'action_chain_verdict': actionChain,
        'work_receipt_verdict': workReceipt,
        'audit_verdict': audit,
        'audit_subject_verdict': auditSubject,
        'receipt_verification_verdict': receiptVerification,
        if (verifiedFields != null) 'verified_fields': verifiedFields,
      },
      'declared_access': declaredAccess ?? {'verdict': accessVerdict},
      'source_pointers': const [],
      'does_not_prove': const [],
    };

Map<String, Object?> _fixture(String name) => Map<String, Object?>.from(
      jsonDecode(File('test/fixtures/$name').readAsStringSync()) as Map,
    );
