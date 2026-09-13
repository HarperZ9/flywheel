import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:flywheel_desktop/models/inspect_evidence_models.dart';

const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _grant = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding(_journey, _head);

void main() {
  test('uploadInspectEvidence sends raw authenticated bytes and no path',
      () async {
    final spy = _InspectSpy((request) {
      expect(request.method, 'POST');
      expect(request.url.path, '/api/import/inspect');
      expect(request.headers['Authorization'], 'Bearer tok-inspect');
      expect(request.headers['Content-Type'], 'application/json');
      expect(request.headers['X-Flywheel-Journey-Ref'], _journey);
      expect(request.headers['X-Flywheel-Expected-Event-Head'], _head);
      expect(request.headers['X-Flywheel-Grant-Ref'], _grant);
      expect(request.headers['X-Flywheel-Inspect-Filename'], 'run.json');
      expect(request.headers.values.join('\n'), isNot(contains('C:')));
      expect(request.bodyBytes, utf8.encode('{"ok":true}'));
      return _successBody(request.headers['X-Flywheel-Inspect-Sha256']!);
    });
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: AuthedClient(spy, readToken: () => 'tok-inspect'),
    );
    final upload = InspectEvidenceUpload.fromBytes(
      Uint8List.fromList(utf8.encode('{"ok":true}')),
      filename: 'run.json',
      clientRequestId: 'inspect-test-1',
    );

    final result = await client.uploadInspectEvidence(
      upload,
      binding: _binding,
      grantRef: _grant,
    );

    expect(spy.seen, 1);
    expect(result.errorCode, isNull);
    expect(result.report?.semanticVerification, 'UNVERIFIABLE');
    expect(result.report?.rows.first.pointer, '/status');
    expect(result.report?.rows.first.sourceValueText, 'success');
    expect(result.stored?.kind, 'inspect-evidence');
  });

  test('uploadInspectEvidence rejects over limit before sending HTTP',
      () async {
    final spy = _InspectSpy((_) => fail('HTTP must not be called'));
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: spy,
    );
    final upload = InspectEvidenceUpload.forTest(
      bytes: Uint8List(maxInspectEvidenceUploadBytes + 1),
      sha256: _repeat('0', 64),
      byteLength: maxInspectEvidenceUploadBytes + 1,
      clientRequestId: 'inspect-test-2',
    );

    await expectLater(
      client.uploadInspectEvidence(upload, binding: _binding, grantRef: _grant),
      throwsA(isA<InspectEvidenceUploadException>()
          .having((error) => error.code, 'code', 'PAYLOAD_TOO_LARGE')),
    );
    expect(spy.seen, 0);
  });

  test('uploadInspectEvidence parses fixed error envelopes', () async {
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: _InspectSpy(
        (_) => {
          'schema': 'flywheel.evidence-transport-error/v1',
          'error': {
            'code': 'SOURCE_DIGEST_MISMATCH',
            'message': 'Inspect upload digest does not match approval',
          },
        },
        statusCode: 409,
      ),
    );
    final upload = InspectEvidenceUpload.fromBytes(
      Uint8List.fromList(utf8.encode('{"ok":true}')),
      clientRequestId: 'inspect-test-3',
    );

    final result = await client.uploadInspectEvidence(
      upload,
      binding: _binding,
      grantRef: _grant,
    );

    expect(result.errorCode, 'SOURCE_DIGEST_MISMATCH');
    expect(result.report, isNull);
  });

  test('uploadInspectEvidence rejects non-200 success-looking bodies',
      () async {
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: _InspectSpy(
        (_) => _successBody(_repeat('a', 64)),
        statusCode: 409,
      ),
    );
    final upload = InspectEvidenceUpload.fromBytes(
      Uint8List.fromList(utf8.encode('{"ok":true}')),
      clientRequestId: 'inspect-test-4',
    );

    final result = await client.uploadInspectEvidence(
      upload,
      binding: _binding,
      grantRef: _grant,
    );

    expect(result.errorCode, 'GATEWAY_ERROR');
    expect(result.report, isNull);
  });

  test('uploadInspectEvidence rejects digest mismatches and malformed receipts',
      () async {
    final malformed = _successBody(_repeat('a', 64))
      ..['stored'] = {'kind': 'inspect-evidence'};
    expect(
        InspectImportResult.fromJson(malformed).errorCode, 'INVALID_RESPONSE');

    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: _InspectSpy((_) => _successBody(_repeat('a', 64))),
    );
    final upload = InspectEvidenceUpload.fromBytes(
      Uint8List.fromList(utf8.encode('{"ok":true}')),
      clientRequestId: 'inspect-test-5',
    );

    final result = await client.uploadInspectEvidence(
      upload,
      binding: _binding,
      grantRef: _grant,
    );

    expect(result.errorCode, 'SOURCE_DIGEST_MISMATCH');
    expect(result.report, isNull);
  });

  test('uploadInspectEvidence times out and cancels stalled response body',
      () async {
    final stalled = _StalledBodyClient();
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: stalled,
    );
    final upload = InspectEvidenceUpload.fromBytes(
      Uint8List.fromList(utf8.encode('{"ok":true}')),
      clientRequestId: 'inspect-test-6',
    );

    final result = await client.uploadInspectEvidence(
      upload,
      binding: _binding,
      grantRef: _grant,
      timeout: const Duration(milliseconds: 5),
    );

    expect(result.errorCode, 'GATEWAY_TIMEOUT');
    await expectLater(stalled.cancelled.future, completes);
  });

  test('inspect import list and read use bounded GET routes', () async {
    final paths = <String>[];
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: _InspectSpy((request) {
        paths.add('${request.url.path}?${request.url.query}');
        if (request.url.path == '/api/import/inspect') {
          return {
            'schema': 'flywheel.inspect-import-list/v1',
            'items': [
              {
                'eid': 'eid-1',
                'source': {
                  'sha256': _repeat('a', 64),
                  'byte_length': 11,
                },
                'reported_status': 'success',
                'stored': {'sha256': _repeat('b', 64)},
              }
            ],
          };
        }
        return _successBody(_repeat('a', 64));
      }),
    );

    final list = await client.listInspectEvidenceImports(limit: 10);
    final read = await client.readInspectEvidenceImport('eid-1');

    expect(
        paths, ['/api/import/inspect?limit=10', '/api/import/inspect/eid-1?']);
    expect(list.items.single.eid, 'eid-1');
    expect(read.report?.semanticVerification, 'UNVERIFIABLE');
  });
}

Map<String, Object?> _successBody(String sha) => {
      'schema': 'flywheel.inspect-import-result/v1',
      'source': {
        'format': 'inspect-json',
        'sha256': sha,
        'byte_length': 11,
        'filename': 'run.json',
      },
      'data_ref': 'data_inspect.source:${sha.substring(0, 32)}',
      'report': {
        'schema': 'flywheel.inspect-evidence/v1',
        'source': {'sha256': sha, 'byte_length': 11},
        'producer': {'format': 'inspect-json', 'version': 2},
        'reported_status': 'success',
        'assessment': 'reported',
        'invalidated': false,
        'semantic_verification': 'UNVERIFIABLE',
        'counts': {
          'total_samples': 1,
          'completed_samples': 1,
          'observed_samples': 1,
        },
        'scoring_coverage': {
          'coverage_complete': true,
          'samples_with_scores': 1,
          'sample_score_records': 1,
          'result_scores': [
            {
              'name': 'accuracy',
              'scorer': 'accuracy',
              'scored_samples': 1,
              'unscored_samples': 0,
            }
          ],
        },
        'samples': [
          {
            'id': 'case-1',
            'epoch': 1,
            'status': null,
            'error': null,
            'scores': [
              {'scorer': 'accuracy', 'value': 0.75}
            ],
          }
        ],
        'source_pointers': [
          {'json_pointer': '/status', 'source_value': 'success'},
          {
            'json_pointer': '/samples/0/scores/accuracy/value',
            'source_value': 0.75,
          }
        ],
      },
      'stored': {
        'kind': 'inspect-evidence',
        'eid': 'eid-1',
        'sha256': _repeat('b', 64),
        'chain_hash': _repeat('c', 64),
      },
    };

String _repeat(String value, int count) => List.filled(count, value).join();

class _InspectSpy extends http.BaseClient {
  _InspectSpy(this.reply, {this.statusCode = 200});

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

class _StalledBodyClient extends http.BaseClient {
  final cancelled = Completer<void>();

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    late StreamController<List<int>> controller;
    controller = StreamController<List<int>>(
      onListen: () => controller.add(utf8.encode('{')),
      onCancel: () {
        if (!cancelled.isCompleted) cancelled.complete();
      },
    );
    return http.StreamedResponse(
      controller.stream,
      200,
      request: request,
      headers: {'content-type': 'application/json'},
    );
  }
}
