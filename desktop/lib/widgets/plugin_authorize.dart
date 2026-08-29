// plugin_authorize.dart — one exact-operation authorization for the Plugins
// view. Builds the gateway operation, shows the grant sheet, and posts the
// approved body. Split out to hold the Plugins view under its size gate.

import 'package:flutter/widgets.dart';

import '../client/gateway_client.dart';
import 'operation_grant_sheet.dart';

/// Authorizes and dispatches one plugin operation. Returns the gateway
/// response, or null when the operator declines the grant.
Future<Map<String, dynamic>?> authorizePluginOperation(
  BuildContext context,
  GatewayClient client,
  String requestId,
  String action,
  Map<String, Object?> raw,
  String path, {
  List<String> credentialRefs = const [],
  Map<String, Object?> Function()? currentRaw,
}) {
  GatewayOperation exact(Map<String, Object?> value) => GatewayOperation.exact(
        action: action,
        operation: value,
        credentialRefs: credentialRefs,
        clientRequestId: requestId,
      );
  final operation = exact(raw);
  return authorizeGatewayOperation(
      context, operation, (body) => client.postJson(path, body),
      currentOperation: () {
    try {
      return currentRaw == null ? operation : exact(currentRaw());
    } catch (_) {
      return null;
    }
  });
}
