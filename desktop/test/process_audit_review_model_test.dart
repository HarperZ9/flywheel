import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/process_audit_review.dart';

void main() {
  test('upload detects an outer command report and sends only audit_packet', () {
    final packet = {
      'schema': 'flywheel.incident-sim-process-audit/v1',
      'source_values': {'target_state': 'closed'},
    };
    final outer = {
      'schema': 'flywheel.incident-sim-command/v1',
      'audit_packet': packet,
    };

    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      Uint8List.fromList(utf8.encode(jsonEncode(outer))),
      filename: 'command.json',
    );

    expect(upload.detectedFormat, 'outer-command-report');
    expect(utf8.decode(upload.bytes), jsonEncode(packet));
    expect(upload.filename, 'command.json');
    expect(upload.locationFor('/source_values/target_state')?.line, 1);
    expect(upload.locationFor('/source_values/target_state')?.context, '"closed"');
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
}
