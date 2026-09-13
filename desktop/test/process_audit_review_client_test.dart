import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/process_audit_review.dart';

void main() {
  test('reviewProcessAuditPacket posts authenticated inner packet bytes',
      () async {
    const packetText = '{\n'
        '  "schema" : "flywheel.incident-sim-process-audit/v1",\n'
        '  "source_values" : {"target_state" : "closed"}\n'
        '}';
    final packet = utf8.encode(packetText);
    final outer = utf8.encode(
      '{"schema":"flywheel.incident-sim-command/v1",'
      '"audit_packet":$packetText}',
    );
    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      Uint8List.fromList(outer),
      filename: 'command.json',
    );
    final spy = _ProcessAuditSpy((request) {
      expect(request.method, 'POST');
      expect(request.url.path, '/api/incident-sim/process-audit/review');
      expect(request.headers['Authorization'], 'Bearer tok-process-audit');
      expect(request.headers['Content-Type'], 'application/json');
      expect(request.headers['X-Flywheel-Grant-Ref'], isNull);
      expect(request.headers.values.join('\n'), isNot(contains('C:')));
      expect(request.bodyBytes, packet);
      return _reviewBody(upload.sha256, upload.byteLength);
    });
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: AuthedClient(spy, readToken: () => 'tok-process-audit'),
    );

    final result = await client.reviewProcessAuditPacket(upload);

    expect(spy.seen, 1);
    expect(result.errorCode, isNull);
    expect(result.assessment, 'packet-local-match');
    expect(result.semanticVerification, 'UNVERIFIABLE');
    expect(result.declaredAccess.verdict, 'NOT_ASSESSED');
    expect(result.sourcePointers.single.pointer, '/source_values/target_state');
    expect(result.sourcePointers.single.sourceValueText, 'closed');
  });

  test('reviewProcessAuditPacket keeps transport errors as review results',
      () async {
    final upload = ProcessAuditPacketUpload.fromPickedBytes(
      Uint8List.fromList(utf8.encode(
        '{"schema":"flywheel.incident-sim-process-audit/v1"}',
      )),
    );
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: _ProcessAuditSpy(
        (_) => {
          'schema': 'flywheel.evidence-transport-error/v1',
          'error': {
            'code': 'INVALID_PACKET',
            'message': 'request body is not a process-audit packet',
          },
        },
        statusCode: 422,
      ),
    );

    final result = await client.reviewProcessAuditPacket(upload);

    expect(result.errorCode, 'INVALID_PACKET');
    expect(result.source, isNull);
  });
}

Map<String, Object?> _reviewBody(String sha, int byteLength) => {
      'schema': ProcessAuditReviewResult.schemaName,
      'source': {
        'format': 'incident-sim-process-audit-json',
        'sha256': sha,
        'byte_length': byteLength,
      },
      'assessment': 'packet-local-match',
      'semantic_verification': 'UNVERIFIABLE',
      'verification': {
        'schema': 'flywheel.incident-sim-process-audit-verification/v1',
        'verdict': 'MATCH',
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
      },
      'declared_access': {
        'verdict': 'NOT_ASSESSED',
        'coverage_assessment': 'not_assessed',
        'limits': [
          'institutional_access component absent; declared access coverage was not assessed',
        ],
      },
      'source_pointers': [
        {
          'json_pointer': '/source_values/target_state',
          'source_value': 'closed'
        },
      ],
      'does_not_prove': ['semantic correctness of the task or trace'],
    };

class _ProcessAuditSpy extends http.BaseClient {
  _ProcessAuditSpy(this.reply, {this.statusCode = 200});

  final Map<String, Object?> Function(http.Request request) reply;
  final int statusCode;
  int seen = 0;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    seen += 1;
    final typed = request as http.Request;
    return http.StreamedResponse(
      Stream.value(utf8.encode(jsonEncode(reply(typed)))),
      statusCode,
      headers: {'content-type': 'application/json'},
    );
  }
}
