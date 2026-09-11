import 'package:flutter/widgets.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../models/operation_models.dart';
import '../models/rowan_walkthrough_models.dart';
import 'gateway_operation_controller.dart';

abstract interface class RowanWalkthroughOperationHost implements Listenable {
  GatewayClient get client;
  List<EndpointRow> get endpoints;
  String? get endpoint;
  String? get selectedModel;
  String? get workspaceRoot;
  bool get authorizing;
  bool get active;
  String? get error;
  List<Map<String, dynamic>> get progress;
  OperationSnapshot? get snapshot;
  OperationResult? get terminalResult;

  Future<void> loadEndpoints();
  Future<bool> recoverFromSession();
  void setEndpoint(String? value);
  void setModel(String value);
  void setWorkspaceRoot(String value);
  void configureScenario(RowanWalkthroughScenario scenario);
  Future<GatewayAuthorizationOutcome<bool>> start(
    BuildContext context,
    String goal, {
    Map<String, Object?>? continuation,
  });
  Future<void> stop(BuildContext context);
  Future<void> reconnect(OperationSnapshot hint);
}
