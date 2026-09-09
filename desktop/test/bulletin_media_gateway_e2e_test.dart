import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/bulletin_media_api.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/bulletin_media_models.dart';
import 'package:http/http.dart' as http;

const _definedConfig = String.fromEnvironment('BULLETIN_GATEWAY_FIXTURE');
const _definedReceipt = String.fromEnvironment('BULLETIN_GATEWAY_E2E_RECEIPT');

void main() {
  test('Dart client drives real gateway media review through one grant',
      () async {
    final configPath = _configured('BULLETIN_GATEWAY_FIXTURE', _definedConfig);
    if (configPath.isEmpty) {
      markTestSkipped('run tool/run_bulletin_media_gateway_e2e.ps1');
      return;
    }
    final config =
        jsonDecode(File(configPath).readAsStringSync()) as Map<String, dynamic>;
    final tracingClient =
        _TracingBearerClient(http.Client(), config['token'] as String);
    final client = GatewayClient(
      baseUrl: config['base_url'] as String,
      httpClient: tracingClient,
    );
    final trace = tracingClient.trace;
    try {
      final api = GatewayBulletinMediaApi(client);
      final runs = await api.listRuns();
      expect(runs.single.runId, config['run_id']);
      expect(runs.single.artifactCount, 1);

      final artifacts = await api.listArtifacts(runs.single.runId);
      expect(artifacts.single.artifactId, config['artifact_id']);
      expect(artifacts.single.invalidResponse, isFalse);

      final draft = BulletinMediaDraft(
        runId: runs.single.runId,
        journeyRef: config['journey_ref'] as String,
        eventHead: config['event_head'] as String,
        clientRequestId: 'dart-real-gateway-media-1',
        credentialRef: config['credential_ref'] as String,
        destination: Uri.parse(config['bulletin_base_url'] as String),
        room: 'findings',
        title: 'Dart selected synth sketch',
        description: 'A public creative artifact selected by run ID.',
        sourceAttribution: 'Created by the owner during a selected run.',
        limits: const [
          'Upload success does not prove license, authorship, malware safety, or hidden-data absence'
        ],
        media: [
          BulletinSelectedMedia(
              artifacts.single, 'Cover art from the selected creative run.')
        ],
      );
      expect(draft.valid, isTrue);

      final preview = await api.previewDraft(draft);
      expect(preview.canDispatch, isTrue);
      expect(preview.review.items.single.attachment.sha256,
          artifacts.single.sha256);
      await _setFixturePreview(config, trace, preview.operation!.operation);
      final bytes = await api.previewBytes(
        preview.proposal.proposalRef,
        preview.review.items.single.preview.previewRef,
        preview.review.previewSha256,
      );
      expect(bytes.statusCode, 200);
      expect(sha256.convert(bytes.bodyBytes).toString(),
          preview.review.items.single.attachment.sha256);

      final approval = await client.postJson('/api/gateway-grants/approve-once',
          {'proposal_ref': preview.proposal.proposalRef});
      expect(approval['grant_ref'], preview.proposal.plannedGrantRef);
      final result = await api.publish(preview.operation!.finalBody(
        GatewayJourneyBinding(
          config['journey_ref'] as String,
          config['event_head'] as String,
        ),
        approval['grant_ref'] as String,
      ));
      expect(result.complete, isTrue);

      final receiptPath =
          _configured('BULLETIN_GATEWAY_E2E_RECEIPT', _definedReceipt);
      if (receiptPath.isNotEmpty) {
        File(receiptPath)
          ..parent.createSync(recursive: true)
          ..writeAsStringSync(jsonEncode({
            'schema': 'flywheel.bulletin-media-dart-gateway-e2e/v1',
            'run_id': runs.single.runId,
            'artifact_id': artifacts.single.artifactId,
            'proposal_ref': preview.proposal.proposalRef,
            'grant_ref': approval['grant_ref'],
            'preview_bytes': bytes.bodyBytes.length,
            'preview_sha256': preview.review.previewSha256,
            'result_state': result.rawState,
            'complete': result.complete,
            'trace': trace,
          }));
      }
    } on Object catch (error) {
      final receiptPath =
          _configured('BULLETIN_GATEWAY_E2E_RECEIPT', _definedReceipt);
      if (receiptPath.isNotEmpty) {
        File(receiptPath)
          ..parent.createSync(recursive: true)
          ..writeAsStringSync(jsonEncode({
            'schema': 'flywheel.bulletin-media-dart-gateway-e2e/v1',
            'complete': false,
            'error': error.toString(),
            if (error is GatewayException) ...{
              'gateway_status_code': error.statusCode,
              'gateway_error_code': error.errorCode,
            },
            'trace': trace,
          }));
      }
      rethrow;
    } finally {
      client.close();
    }
  });
}

Future<void> _setFixturePreview(Map<String, dynamic> config,
    List<Map<String, Object?>> trace, Map<String, Object?> operation) async {
  final controlUrl = config['control_url'];
  if (controlUrl is! String || controlUrl.isEmpty) return;
  final response = await http.post(
    Uri.parse('$controlUrl/set-preview'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode(operation['args']),
  );
  trace.add({
    'method': 'POST',
    'path': '/fixture/set-preview',
    'status': response.statusCode,
  });
  expect(response.statusCode, 200);
}

final class _TracingBearerClient extends http.BaseClient {
  final http.Client inner;
  final String token;
  final List<Map<String, Object?>> trace = [];
  _TracingBearerClient(this.inner, this.token);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    request.headers['Authorization'] = 'Bearer $token';
    final response = await inner.send(request);
    final bytes = await response.stream.toBytes();
    trace.add({
      'method': request.method,
      'path': request.url.path,
      'status': response.statusCode,
      'body': utf8.decode(bytes, allowMalformed: true),
    });
    return http.StreamedResponse(
        Stream<List<int>>.value(bytes), response.statusCode,
        contentLength: bytes.length,
        request: response.request,
        headers: response.headers,
        isRedirect: response.isRedirect,
        persistentConnection: response.persistentConnection,
        reasonPhrase: response.reasonPhrase);
  }

  @override
  void close() => inner.close();
}

String _configured(String envName, String defined) =>
    defined.isNotEmpty ? defined : Platform.environment[envName] ?? '';
