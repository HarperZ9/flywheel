import 'package:flutter/widgets.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../models/operation_models.dart';
import '../models/rowan_walkthrough_models.dart';
import 'gateway_operation_controller.dart';
import 'rowan_operation_controller.dart';
import 'rowan_walkthrough_operation_host.dart';

final class RowanOperationHostAdapter extends ChangeNotifier
    implements RowanWalkthroughOperationHost {
  RowanOperationHostAdapter(this._controller) {
    _controller.addListener(notifyListeners);
  }

  final RowanOperationController _controller;

  @override
  GatewayClient get client => _controller.client;
  @override
  List<EndpointRow> get endpoints => _controller.endpoints;
  @override
  String? get endpoint => _controller.endpoint;
  @override
  String? get selectedModel => _controller.selectedModel;
  @override
  String? get workspaceRoot => _controller.workspaceRoot;
  @override
  bool get authorizing => _controller.authorizing;
  @override
  bool get active => _controller.active;
  @override
  String? get error => _controller.error;
  @override
  List<Map<String, dynamic>> get progress => _controller.progress;
  @override
  OperationSnapshot? get snapshot => _controller.snapshot;
  @override
  OperationResult? get terminalResult => _controller.terminalResult;

  @override
  Future<void> loadEndpoints() => _controller.loadEndpoints();
  @override
  Future<bool> recoverFromSession() => _controller.recoverFromSession();
  @override
  void setEndpoint(String? value) => _controller.setEndpoint(value);
  @override
  void setModel(String value) => _controller.setModel(value);
  @override
  void setWorkspaceRoot(String value) => _controller.setWorkspaceRoot(value);

  @override
  void configureScenario(RowanWalkthroughScenario scenario) {
    _controller
      ..setMaxStepsOverride(scenario.maxSteps)
      ..setMaxTokens(scenario.maxTokens)
      ..setTimeoutSeconds(scenario.timeoutSeconds)
      ..setAllowWrite(false)
      ..setAllowExec(false);
  }

  @override
  Future<GatewayAuthorizationOutcome<bool>> start(
    BuildContext context,
    String goal, {
    Map<String, Object?>? continuation,
  }) =>
      _controller.start(context, goal, continuation: continuation);

  @override
  Future<void> stop(BuildContext context) => _controller.stop(context);
  @override
  Future<void> reconnect(OperationSnapshot hint) => _controller.reconnect(hint);

  @override
  void dispose() {
    _controller.removeListener(notifyListeners);
    super.dispose();
  }
}
