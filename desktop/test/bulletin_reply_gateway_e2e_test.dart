import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:http/http.dart' as http;

const _config = String.fromEnvironment('BULLETIN_REPLY_FIXTURE');
const _receipt = String.fromEnvironment('BULLETIN_REPLY_RECEIPT');

void main() {
  test('native client publishes replies with one exact grant on a real Worker',
      () async {
    final path = _config.isNotEmpty
        ? _config
        : Platform.environment['BULLETIN_REPLY_FIXTURE'] ?? '';
    if (path.isEmpty) {
      markTestSkipped('requires the actual Worker gateway fixture; see docs');
      return;
    }
    final config = jsonDecode(File(path).readAsStringSync()) as Map;
    expect(config['mode'], 'actual_worker_loopback');
    final bearer = _BearerClient(config['token'] as String);
    final client = GatewayClient(
        baseUrl: config['base_url'] as String, httpClient: bearer);
    final binding = GatewayJourneyBinding(
        config['journey_ref'] as String, config['event_head'] as String);
    final board = config['bulletin_base_url'] as String;
    expect(Uri.parse(board).host, '127.0.0.1');
    final negatives = <String, int>{};
    GatewayOperation operation(String request, Map<String, Object?> post) =>
        GatewayOperation.exact(
            action: 'lane.call',
            clientRequestId: request,
            credentialRefs: [
              config['credential_ref'] as String
            ],
            operation: {
              'name': 'bulletin',
              'tool': 'board_write_post',
              'args': post,
              'governance_tier': 'T2',
              'timeout': 20,
            });
    Future<Map<String, dynamic>> approve(GatewayOperation op) async {
      final proposed = await client.postJson(
          '/api/gateway-grants/prepare/lane.call', op.prepareBody(binding));
      final grant = await client.postJson('/api/gateway-grants/approve-once',
          {'proposal_ref': proposed['proposal_ref']});
      return op.finalBody(binding, grant['grant_ref'] as String);
    }

    Future<Map<String, dynamic>> publish(Map<String, dynamic> body) =>
        client.postJson('/api/lane/bulletin/board_write_post', body);
    Future<Map> readPost(String id) async {
      final response = await http.get(Uri.parse('$board/v1/posts/$id'));
      expect(response.statusCode, 200);
      return jsonDecode(response.body)['post'] as Map;
    }

    try {
      final root = await publish(await approve(operation('reply-root',
          {'room': 'findings', 'body': 'Public synthetic evaluation task.'})));
      expect(root['status'], 'posted_readback_match');
      final rootId = root['post_id'] as String;
      final parent = await readPost(rootId);
      expect(parent['parent_id'], isNull);
      final expected = {
        'room': 'findings',
        'body': 'Public synthetic task result. No model evaluation is claimed.',
        'parent_id': rootId,
      };
      final finalBody = await approve(operation('reply-result', expected));
      Future<void> denied(String label, Map<String, dynamic> changed) async {
        try {
          await publish(changed);
          fail('$label reached publication');
        } on GatewayException catch (error) {
          expect(error.statusCode, anyOf(403, 409));
          negatives[label] = error.statusCode!;
        }
      }

      for (final change in {
        'parent_id': '1788991200000-otherone',
        'room': 'general',
        'body': 'A different task result.',
      }.entries) {
        await denied(change.key, {
          ...finalBody,
          'args': {...expected, change.key: change.value},
        });
      }
      await denied(
          'request', {...finalBody, 'client_request_id': 'another-task'});
      await denied('journey', {
        ...finalBody,
        'journey_ref': 'jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
      });
      final reply = await publish(finalBody);
      expect(reply['status'], 'posted_readback_match');
      final replyId = reply['post_id'] as String;
      expect(replyId, isNot(rootId));
      final observed = await readPost(replyId);
      for (final field in expected.entries) {
        expect(observed[field.key], field.value);
      }
      expect(observed['author'], parent['author']);
      expect(observed['author'], isA<String>());
      await denied('grant_replay', finalBody);
      final feedResponse = await http.get(Uri.parse('$board/v1/feed').replace(
          queryParameters: {
            'author': observed['author'] as String,
            'limit': '100'
          }));
      expect(feedResponse.statusCode, 200);
      final feed = jsonDecode(feedResponse.body) as Map;
      expect(feed['next_before'], isNull);
      final rows = feed['posts'] as List;
      expect(rows.map((row) => row['id']).toSet(), {rootId, replyId});
      final out = _receipt.isNotEmpty
          ? _receipt
          : Platform.environment['BULLETIN_REPLY_RECEIPT'] ?? '';
      if (out.isNotEmpty) {
        File(out).writeAsStringSync(jsonEncode({
          'schema': 'flywheel.bulletin-native-reply-e2e/v1',
          'complete': true,
          'fixture_mode': config['mode'],
          'parent_id': rootId,
          'reply_id': replyId,
          'author': observed['author'],
          'observed_post_count': rows.length,
          'negative_statuses': negatives,
          'does_not_prove': [
            'live model behavior',
            'whole-host observation',
            'agent alignment'
          ],
        }));
      }
    } finally {
      client.close();
    }
  }, timeout: const Timeout(Duration(minutes: 2)));
}

final class _BearerClient extends http.BaseClient {
  final _inner = http.Client();
  final String token;
  _BearerClient(this.token);
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    request.headers['Authorization'] = 'Bearer $token';
    final response = await _inner.send(request);
    final bytes = await response.stream.toBytes();
    // Public error codes and paths only; never log request headers or bodies.
    final error = response.statusCode >= 400
        ? GatewayException.fromResponse(response.statusCode, utf8.decode(bytes))
        : null;
    // ignore: avoid_print
    print(
        '${request.url.path}: ${response.statusCode} ${error?.errorCode ?? ""}');
    return http.StreamedResponse(Stream.value(bytes), response.statusCode,
        headers: response.headers, request: response.request);
  }

  @override
  void close() => _inner.close();
}
