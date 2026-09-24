import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';

import 'package:flywheel_desktop/assistant/assistant_executor.dart';
import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/services/connection_config.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';

const _definedRunId = String.fromEnvironment('FLYWHEEL_ANDROID_HANDOFF_RUN_ID');
const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    _journey = 'jrn_$_a',
    _operation = 'op_$_a',
    _head = '$_a$_a',
    _grant = 'gnt_$_a';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('paired Android gateway handoff uses token and avoids duplicate',
      (tester) async {
    late BuildContext context;
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: GatewayOperationScope(
        authorize: (_, operation, current, dispatch) async {
          final active = current();
          if (active == null) return const GatewayAuthorizationOutcome.denied();
          return GatewayAuthorizationOutcome.value(await dispatch(
            operation.finalBody(
              const GatewayJourneyBinding(_journey, _head),
              _grant,
            ),
          ));
        },
        child: Builder(builder: (ctx) {
          context = ctx;
          return const SizedBox.shrink();
        }),
      ),
    ));

    await tester.runAsync(() async {
      final fixture = await _GatewayFixture.start();
      final token = _ephemeralToken();
      fixture.token = token;
      final root = Directory.systemTemp.createTempSync('fw-android-handoff-');
      final httpClient = http.Client();
      addTearDown(() async {
        httpClient.close();
        await fixture.close();
        if (root.existsSync()) root.deleteSync(recursive: true);
      });

      final store = ConnectionStore(file: File('${root.path}/connection.json'))
        ..save(ConnectionConfig(baseUrl: fixture.baseUrl, token: token));
      final config = store.load();
      final client = GatewayClient(
        baseUrl: config.effectiveBaseUrl,
        httpClient: AuthedClient(httpClient, readToken: config.tokenSource),
      );
      final unauthenticatedHttp = http.Client();
      addTearDown(unauthenticatedHttp.close);
      final wrongTokenHttp = http.Client();
      addTearDown(wrongTokenHttp.close);

      final unauthenticated = await GatewayClient(
        baseUrl: fixture.baseUrl,
        httpClient: unauthenticatedHttp,
      ).isAlive();
      expect(unauthenticated, isFalse);
      final wrongToken = await GatewayClient(
        baseUrl: fixture.baseUrl,
        httpClient:
            AuthedClient(wrongTokenHttp, readToken: () => 'wrong-token'),
      ).isAlive();
      expect(wrongToken, isFalse);
      expect(await client.isAlive(), isTrue);
      expect(fixture.unauthorizedRequests, 2);

      fixture.relayUnavailable = true;
      final assistant = AssistantExecutor(
        agent: GatewayAgentSink(client),
        device: PreviewDeviceSink(),
      );
      final noResponse = await assistant.handle('inspect the release');
      expect(noResponse.ok, isFalse);
      expect(noResponse.runId, isNull);
      expect(fixture.relayStartPosts, 1);
      final unreachableHttp = http.Client();
      addTearDown(unreachableHttp.close);
      final unreachable = await AssistantExecutor(
        agent: GatewayAgentSink(GatewayClient(
          baseUrl: 'http://127.0.0.1:1',
          httpClient: unreachableHttp,
        )),
        device: PreviewDeviceSink(),
      ).handle('inspect the release');
      expect(unreachable.ok, isFalse);

      final sessionStore = JourneySessionStore(
        file: File('${root.path}/journey-session.json'),
      )..save(JourneySession(journeyRef: _journey, lens: JourneyLens.verify));
      final rowan = RowanOperationController(client, sessionStore: sessionStore)
        ..setEndpoint('local');
      addTearDown(rowan.dispose);
      if (!context.mounted) {
        throw StateError('gateway operation test context unmounted');
      }
      final started = await rowan.start(context, 'handoff from phone');
      expect(started.value, isTrue);
      await Future<void>.delayed(const Duration(seconds: 1));
      final requestSha = sessionStore.load()?.operationRequestSha256;
      expect(requestSha, isNotNull);
      expect(fixture.agentPosts, 1);

      fixture.requestSha256 = requestSha;
      final recovered =
          RowanOperationController(client, sessionStore: sessionStore);
      addTearDown(recovered.dispose);
      expect(await recovered.recoverFromSession(), isTrue);
      expect(fixture.agentPosts, 1,
          reason: 'recovery must not submit a duplicate operation');
      expect(fixture.operationSnapshotReads, greaterThanOrEqualTo(1));
      expect(fixture.operationResultReads, greaterThanOrEqualTo(1));

      final receipt = {
        'schema': 'flywheel.android-gateway-handoff-fixture/v1',
        'run_id': _runId(),
        'platform': Platform.operatingSystem,
        'scope':
            'self-contained integration_test gateway; not installed release app acceptance',
        'token_material': 'generated-and-redacted',
        'gateway': {
          'unauthorized_requests': fixture.unauthorizedRequests,
          'world_gets': fixture.worldGets,
          'relay_start_posts': fixture.relayStartPosts,
          'agent_posts': fixture.agentPosts,
          'operation_list_reads': fixture.operationListReads,
          'operation_snapshot_reads': fixture.operationSnapshotReads,
          'operation_result_reads': fixture.operationResultReads,
        },
        'cases': {
          'paired_world_read': {'passed': true},
          'missing_token_rejected': {'passed': true, 'ok': unauthenticated},
          'wrong_token_rejected': {'passed': true, 'ok': wrongToken},
          'unreachable_gateway': {'passed': true, 'ok': unreachable.ok},
          'assistant_no_response': {'passed': true, 'ok': noResponse.ok, 'server_posts': fixture.relayStartPosts},
          'duplicate_after_restart': {'passed': true, 'operation_ref': _operation, 'server_agent_posts': fixture.agentPosts, 'request_hash_bound': requestSha != null},
        },
        'limits': [
          'uses fixture gateway in the test process',
          'does not install or validate the operator release build',
          'does not call model providers or live Relay/Plexus services',
        ],
      };
      final encoded = jsonEncode(receipt);
      expect(encoded, isNot(contains(token)));
      // ignore: avoid_print
      print('FLYWHEEL_ANDROID_HANDOFF_RECEIPT_JSON:$encoded');
    });
  });
}

String _runId() => _definedRunId.isNotEmpty ? _definedRunId : 'android_handoff_${DateTime.now().microsecondsSinceEpoch}';

String _ephemeralToken() {
  final random = Random.secure();
  return base64UrlEncode(List<int>.generate(32, (_) => random.nextInt(256))).replaceAll('=', '');
}

OperationResult _result() => OperationResult.fromJson({'schema': operationResultSchema, 'operation_ref': _operation, 'action': 'agent.run', 'state': 'completed', 'result': {'final': 'fixture complete'}});

final class _GatewayFixture {
  _GatewayFixture._(this._server);

  final HttpServer _server;
  String? token;
  String? requestSha256;
  bool relayUnavailable = false;
  int unauthorizedRequests = 0;
  int worldGets = 0;
  int relayStartPosts = 0;
  int agentPosts = 0;
  int operationListReads = 0;
  int operationSnapshotReads = 0;
  int operationResultReads = 0;

  String get baseUrl => 'http://${_server.address.address}:${_server.port}';

  static Future<_GatewayFixture> start() async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final fixture = _GatewayFixture._(server);
    server.listen(fixture._handle);
    return fixture;
  }

  Future<void> close() => _server.close(force: true);

  Future<void> _handle(HttpRequest request) async {
    if (request.headers.value(HttpHeaders.authorizationHeader) !=
        'Bearer $token') {
      unauthorizedRequests++;
      await _json(request.response, 401, {'error': 'unauthorized'});
      return;
    }
    final path = request.uri.path;
    if (request.method == 'GET' && path == '/api/world') {
      worldGets++;
      await _json(request.response, 200, {'ok': true});
    } else if (request.method == 'POST' && path == '/api/relay/start') {
      relayStartPosts++;
      await _discard(request);
      if (relayUnavailable) {
        await _json(request.response, 504, {'error': 'gateway timeout'});
      } else {
        await _json(request.response, 200, {
          'run_id': '0123456789abcdef',
          'state': 'running',
        });
      }
    } else if (request.method == 'POST' && path == '/api/agent') {
      agentPosts++;
      await _discard(request);
      await _operationStream(request.response);
    } else if (request.method == 'GET' &&
        path == '/api/operations' &&
        request.uri.queryParameters['journey_ref'] == _journey) {
      operationListReads++;
      final sha = requestSha256;
      await _json(request.response, 200, {
        'schema': operationListSchema,
        'journey_ref': _journey,
        'event_head_sha256': _head,
        'operations': [_terminalSnapshot()],
        'request_sha256_by_operation': {if (sha != null) _operation: sha},
        'next_cursor': null,
      });
    } else if (request.method == 'GET' &&
        path == '/api/operations/$_operation') {
      operationSnapshotReads++;
      await _json(request.response, 200, _terminalSnapshot());
    } else if (request.method == 'GET' &&
        path == '/api/operations/$_operation/result') {
      operationResultReads++;
      await _json(request.response, 200, _result().toJson());
    } else {
      await _json(request.response, 404, {'error': 'not found'});
    }
  }

  Future<void> _operationStream(HttpResponse response) async {
    response.statusCode = 200;
    response.headers.set(HttpHeaders.contentTypeHeader, 'text/event-stream');
    response.write('id: 1\n');
    response.write('event: terminal\n');
    response.write('data: ${jsonEncode({'snapshot': _terminalSnapshot(), 'result': _result().toJson()})}\n\n');
    response.write('id: 2\n');
    response.write('event: terminal\n');
    response.write('data: [DONE]\n\n');
    await response.close();
  }

  Map<String, Object?> _terminalSnapshot() {
    final result = _result();
    return {
      'schema': operationSnapshotSchema,
      'operation_ref': _operation,
      'journey_ref': _journey,
      'event_head_sha256': _head,
      'state': 'completed',
      'can_cancel': false,
      'terminal_event_ref': 'b' * 64,
      'result_sha256': result.canonicalSha256,
    };
  }
}

Future<void> _discard(HttpRequest request) => utf8.decoder.bind(request).join().then((_) {});

Future<void> _json(HttpResponse response, int status, Map<String, Object?> body) async {
  response.statusCode = status;
  response.headers.contentType = ContentType.json;
  response.write(jsonEncode(body));
  await response.close();
}
