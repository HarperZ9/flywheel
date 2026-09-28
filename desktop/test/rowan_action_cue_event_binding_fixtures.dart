import 'package:flutter/widgets.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_event_binding.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_walkthrough_operation_host.dart';
import 'package:flywheel_desktop/models/agent_execution_mode.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/models/rowan_walkthrough_models.dart';

import 'rowan_action_cue_controller_fixtures.dart';

final class BindingOperationHost extends ChangeNotifier
    implements RowanWalkthroughOperationHost {
  BindingOperationHost()
      : client = GatewayClient(baseUrl: 'https://rowan.invalid');

  @override
  final GatewayClient client;
  @override
  List<EndpointRow> endpoints = const [];
  @override
  String? endpoint = 'ollama';
  @override
  AgentExecutionMode executionMode = AgentExecutionMode.api;
  @override
  String? selectedModel = 'qwen-test';
  @override
  String? workspaceRoot = '/workspace';
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

  var removedListeners = 0;

  void observe({
    OperationSnapshot? snapshot,
    bool active = false,
    bool authorizing = false,
    String? error,
  }) {
    this.snapshot = snapshot;
    this.active = active;
    this.authorizing = authorizing;
    this.error = error;
    notifyListeners();
  }

  @override
  void removeListener(VoidCallback listener) {
    removedListeners += 1;
    super.removeListener(listener);
  }

  @override
  Future<void> loadEndpoints() async {}
  @override
  Future<bool> recoverFromSession() async => false;
  @override
  void setEndpoint(String? value) => endpoint = value;
  @override
  void setExecutionMode(AgentExecutionMode value) => executionMode = value;
  @override
  void setModel(String value) => selectedModel = value;
  @override
  void setWorkspaceRoot(String value) => workspaceRoot = value;
  @override
  void configureScenario(RowanWalkthroughScenario scenario) {}
  @override
  Future<GatewayAuthorizationOutcome<bool>> start(
    BuildContext context,
    String goal, {
    Map<String, Object?>? continuation,
  }) async =>
      const GatewayAuthorizationOutcome.value(true);
  @override
  Future<void> stop(BuildContext context) async {}
  @override
  Future<bool> reconnect(OperationSnapshot hint) async => false;
}

final class BindingScreenSharingSource extends ChangeNotifier
    implements RowanActionCueScreenSharingSource {
  BindingScreenSharingSource(this._snapshot);

  RowanActionCueScreenSharingSnapshot _snapshot;
  var removedListeners = 0;

  @override
  RowanActionCueScreenSharingSnapshot get cueSnapshot => _snapshot;

  void observe(RowanActionCueScreenSharingSnapshot snapshot) {
    _snapshot = snapshot;
    notifyListeners();
  }

  @override
  void removeListener(VoidCallback listener) {
    removedListeners += 1;
    super.removeListener(listener);
  }
}

Future<void> flushCueBinding() async {
  await Future<void>.delayed(Duration.zero);
  await Future<void>.delayed(Duration.zero);
}

OperationSnapshot bindingTerminalCueSnapshot(String state) =>
    OperationSnapshot.fromJson({
      'schema': operationSnapshotSchema,
      'operation_ref': fixtureOperation,
      'journey_ref': fixtureJourney,
      'event_head_sha256': fixtureHeadA,
      'state': state,
      'can_cancel': false,
      'terminal_event_ref': fixtureHeadB,
      'result_sha256': fixtureHeadA,
    });
