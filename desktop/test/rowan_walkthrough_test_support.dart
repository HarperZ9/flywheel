import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_walkthrough_operation_host.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/models/rowan_walkthrough_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const rowanTestA = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const rowanTestHead =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const rowanTestEvent =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const rowanTestOperation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const rowanTestBinding =
    GatewayJourneyBinding('jrn_$rowanTestA', rowanTestHead);
const rowanTestAnswer =
    'The implementation is off-by-one: next_attempt 4 with max_attempts 3 '
    'is allowed, but the rule is next_attempt <= max_attempts.';

FilledButton rowanRunButton(WidgetTester tester) => tester.widget<FilledButton>(
      find.byType(FilledButton).first,
    );

Widget wrapRowanTest(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

class FakeRowanOperationHost extends ChangeNotifier
    implements RowanWalkthroughOperationHost {
  FakeRowanOperationHost() : client = _client();

  @override
  final GatewayClient client;
  @override
  List<EndpointRow> endpoints = const [];
  @override
  String? endpoint;
  @override
  String? selectedModel;
  @override
  String? workspaceRoot;
  @override
  bool authorizing = false;
  @override
  bool active = false;
  @override
  String? error;
  @override
  List<Map<String, dynamic>> progress = const [];
  @override
  OperationSnapshot? snapshot;
  @override
  OperationResult? terminalResult;

  RowanWalkthroughScenario? configuredScenario;
  String? lastGoal;
  int loadCalls = 0;
  int recoverCalls = 0;
  int startCalls = 0;
  int reconnectCalls = 0;
  OperationSnapshot? reconnectedFrom;
  bool failReconnect = false;

  @override
  Future<void> loadEndpoints() async {
    loadCalls += 1;
    endpoints = [
      EndpointRow(
        name: 'ollama',
        backend: 'local',
        credential: 'local-none',
        providerRole: 'local',
        configured: true,
      ),
    ];
    endpoint ??= 'ollama';
    notifyListeners();
  }

  @override
  Future<bool> recoverFromSession() async {
    recoverCalls += 1;
    return false;
  }

  @override
  void setEndpoint(String? value) {
    endpoint = value;
    selectedModel = null;
    notifyListeners();
  }

  @override
  void setModel(String value) {
    selectedModel = value.trim().isEmpty ? null : value.trim();
    notifyListeners();
  }

  @override
  void setWorkspaceRoot(String value) {
    workspaceRoot = value.trim().isEmpty ? null : value.trim();
    notifyListeners();
  }

  @override
  void configureScenario(RowanWalkthroughScenario scenario) {
    configuredScenario = scenario;
  }

  @override
  Future<GatewayAuthorizationOutcome<bool>> start(
    BuildContext context,
    String goal, {
    Map<String, Object?>? continuation,
  }) async {
    startCalls += 1;
    lastGoal = goal;
    if (authorizing || active) {
      return GatewayAuthorizationOutcome.failure(
        const GatewayOperationFailure(
          'OPERATION_ACTIVE',
          'An operation is already active',
        ),
      );
    }
    authorizing = true;
    notifyListeners();
    authorizing = false;
    active = true;
    snapshot = rowanTestSnapshot('running', canCancel: true);
    progress = const [
      {'type': 'started', 'source': 'fake-shared-host'}
    ];
    notifyListeners();
    return const GatewayAuthorizationOutcome.value(true);
  }

  @override
  Future<void> stop(BuildContext context) async {
    active = false;
    snapshot = rowanTestSnapshot('cancelled',
        resultSha256: rowanCancelledResult.canonicalSha256);
    terminalResult = rowanCancelledResult;
    notifyListeners();
  }

  @override
  Future<bool> reconnect(OperationSnapshot hint) async {
    reconnectCalls += 1;
    reconnectedFrom = hint;
    if (failReconnect) return false;
    final result = terminalResult;
    if (result == null) throw StateError('missing terminal result');
    snapshot =
        rowanTestSnapshot('completed', resultSha256: result.canonicalSha256);
    notifyListeners();
    return true;
  }

  void complete(OperationResult result) {
    active = false;
    terminalResult = result;
    snapshot =
        rowanTestSnapshot('completed', resultSha256: result.canonicalSha256);
    progress = List<Map<String, dynamic>>.unmodifiable([
      ...progress,
      {'type': 'done', ...result.result},
    ]);
    notifyListeners();
  }
}

GatewayClient _client() => GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/models') {
          return http.Response(
            jsonEncode({
              'endpoint': 'ollama',
              'models': [
                {'id': 'qwen2.5-coder-14b-instruct', 'default': false},
              ],
              'reason': '',
            }),
            200,
          );
        }
        return http.Response('unexpected ${request.url.path}', 500);
      }),
    );

OperationSnapshot rowanTestSnapshot(String state,
        {bool canCancel = false, String? resultSha256}) =>
    OperationSnapshot.fromJson({
      'schema': operationSnapshotSchema,
      'operation_ref': rowanTestOperation,
      'journey_ref': rowanTestBinding.journeyRef,
      'event_head_sha256': rowanTestEvent,
      'state': state,
      'can_cancel': canCancel,
      'terminal_event_ref':
          {'completed', 'cancelled'}.contains(state) ? rowanTestEvent : null,
      'result_sha256': {'completed', 'cancelled'}.contains(state)
          ? resultSha256 ?? rowanCancelledResult.canonicalSha256
          : null,
    });

OperationResult rowanTestResult(String finalText,
        {String state = 'completed'}) =>
    OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': rowanTestOperation,
      'action': 'agent.run',
      'state': state,
      'result': {'final': finalText},
    });

final rowanCancelledResult = rowanTestResult('cancelled', state: 'cancelled');
