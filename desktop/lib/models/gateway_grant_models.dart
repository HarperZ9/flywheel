import 'evidence_state.dart';
import 'gateway_grant_summary.dart';

export 'gateway_grant_summary.dart';

const gatewayOperationSchema = 'flywheel.gateway-operation/v1';
final _credentialRef = RegExp(r'^cred_[0-9a-f]{32}$');
final _dataRef = RegExp(r'^data_[A-Za-z0-9._:-]{0,123}$');
final _requestId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$');
final _secretKey = RegExp(
    r'(?:^|[_-])(api[_-]?key|token|secret|password|credential)(?:$|[_-])',
    caseSensitive: false);

Never _invalid() => throw ArgumentError('Gateway operation is invalid');

Object? _snapshot(Object? value, List<int> budget, int depth,
    {String key = ''}) {
  if (depth > 16 || --budget[0] < 0) _invalid();
  if (value == null || value is bool || value is int) return value;
  if (value is num) return value.isFinite ? value : _invalid();
  if (value is String) {
    if (!isSafePublicText(value) && key != 'root') _invalid();
    return value;
  }
  if (value is List) {
    return List.unmodifiable(
        value.map((item) => _snapshot(item, budget, depth + 1, key: key)));
  }
  if (value is Map && value.keys.every((item) => item is String)) {
    final result = <String, Object?>{};
    for (final entry in value.entries) {
      final name = entry.key as String;
      if (_secretKey.hasMatch(name) && name != 'credential_refs') _invalid();
      result[name] = _snapshot(entry.value, budget, depth + 1, key: name);
    }
    return Map<String, Object?>.unmodifiable(result);
  }
  return _invalid();
}

final class GatewayOperation {
  final String action, clientRequestId, tool;
  final GatewayDestination destination;
  final Map<String, Object?> operation;
  final List<String> scopes, dataRefs, credentialRefs;

  GatewayOperation._(this.action, this.clientRequestId, this.destination,
      this.tool, Map<String, Object?> raw)
      : operation = _snapshot(raw, [4096], 0) as Map<String, Object?>,
        scopes = List<String>.unmodifiable(_scopes(action, raw)),
        dataRefs = List<String>.unmodifiable(raw['data_refs'] as List<String>),
        credentialRefs =
            List<String>.unmodifiable(raw['credential_refs'] as List<String>) {
    if (!_requestId.hasMatch(clientRequestId) ||
        [destination.kind, destination.ref, tool]
            .any((v) => v.isEmpty || !isSafePublicText(v)) ||
        dataRefs.any((ref) => !_dataRef.hasMatch(ref)) ||
        credentialRefs.any((ref) => !_credentialRef.hasMatch(ref)) ||
        dataRefs.toSet().length != dataRefs.length ||
        credentialRefs.toSet().length != credentialRefs.length) {
      _invalid();
    }
  }

  factory GatewayOperation.pluginProbe(
          {required String name,
          required String clientRequestId,
          List<String> dataRefs = const [],
          List<String> credentialRefs = const []}) =>
      GatewayOperation._withRefs('plugin.probe', clientRequestId,
          GatewayDestination('plugin', name), 'plugin.probe', {'name': name},
          dataRefs: dataRefs, credentialRefs: credentialRefs);

  factory GatewayOperation.pluginCall(
          {required String name,
          required String tool,
          required Map<String, dynamic> arguments,
          required List<String> credentialRefs,
          List<String> dataRefs = const [],
          required String clientRequestId}) =>
      GatewayOperation._withRefs(
          'plugin.call',
          clientRequestId,
          GatewayDestination('plugin', name),
          tool,
          {'name': name, 'tool': tool, 'arguments': arguments},
          dataRefs: dataRefs,
          credentialRefs: credentialRefs);

  factory GatewayOperation.chat(
          String request, String model, List<Map<String, dynamic>> messages,
          {List<String> dataRefs = const [],
          List<String> credentialRefs = const []}) =>
      GatewayOperation._withRefs(
          'chat.complete',
          request,
          GatewayDestination('model', model),
          'chat.complete',
          {'model': model, 'messages': messages, 'stream': true},
          dataRefs: dataRefs,
          credentialRefs: credentialRefs);

  factory GatewayOperation.workflow(
          String request, Map<String, Object?> operation,
          {List<String>? dataRefs, List<String>? credentialRefs}) =>
      GatewayOperation.exact(
          action: 'workflow.run',
          operation: operation,
          clientRequestId: request,
          dataRefs: dataRefs,
          credentialRefs: credentialRefs);

  factory GatewayOperation.exact(
          {required String action,
          required Map<String, Object?> operation,
          required String clientRequestId,
          GatewayDestination? destination,
          String? tool,
          List<String>? dataRefs,
          List<String>? credentialRefs}) =>
      GatewayOperation._withRefs(
          action,
          clientRequestId,
          destination ?? _destination(action, operation),
          tool ?? _tool(action, operation),
          operation,
          dataRefs: dataRefs,
          credentialRefs: credentialRefs);

  factory GatewayOperation._withRefs(String action, String request,
      GatewayDestination destination, String tool, Map<String, Object?> raw,
      {List<String>? dataRefs, List<String>? credentialRefs}) {
    final data = _refs(raw, 'data_refs', dataRefs);
    final credentials = _refs(raw, 'credential_refs', credentialRefs);
    return GatewayOperation._(action, request, destination, tool,
        {...raw, 'data_refs': data, 'credential_refs': credentials});
  }

  Map<String, dynamic> prepareBody(GatewayJourneyBinding binding) => {
        'schema': gatewayOperationSchema,
        'journey_ref': binding.journeyRef,
        'expected_event_head': binding.eventHead,
        'client_request_id': clientRequestId,
        'operation': operation
      };
  Map<String, dynamic> finalBody(GatewayJourneyBinding binding, String grant) =>
      {
        'schema': gatewayOperationSchema,
        'journey_ref': binding.journeyRef,
        'expected_event_head': binding.eventHead,
        'client_request_id': clientRequestId,
        'grant_ref': grant,
        ...operation
      };

  @override
  bool operator ==(Object other) =>
      other is GatewayOperation &&
      action == other.action &&
      clientRequestId == other.clientRequestId &&
      destination == other.destination &&
      tool == other.tool &&
      sameGatewayValue(operation, other.operation);
  @override
  int get hashCode => Object.hash(
      action, clientRequestId, destination, tool, gatewayValueHash(operation));
}

final class GatewayGrantApproval extends DefensiveModel {
  final String grantRef, expiresAt;
  GatewayGrantApproval._(this.grantRef, this.expiresAt, super.parseIssues);
  factory GatewayGrantApproval.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    exactGatewayFields(
        json, const {'schema', 'grant_ref', 'expires_at'}, issues, 'approval');
    expectSchema(json, 'flywheel.operation-grant-approval/v1', issues);
    return GatewayGrantApproval._(
        readText(json, 'grant_ref', issues, pattern: grantRefPattern),
        readText(json, 'expires_at', issues),
        issues);
  }
}

List<String> _refs(
    Map<String, Object?> raw, String field, List<String>? given) {
  final present = raw[field];
  if (present != null &&
      (present is! List || present.any((value) => value is! String))) {
    _invalid();
  }
  final existing = present == null ? null : List<String>.from(present as List);
  if (given != null &&
      existing != null &&
      !sameGatewayStringList(given, existing)) {
    _invalid();
  }
  return List<String>.unmodifiable(given ?? existing ?? const []);
}

GatewayDestination _destination(String action, Map<String, Object?> value) {
  final plugin = action.startsWith('plugin.');
  final market = action.startsWith('marketplace.');
  final field = plugin || market
      ? 'name'
      : action == 'chat.complete'
          ? 'model'
          : 'endpoint';
  final ref = value[field];
  return ref is String
      ? GatewayDestination(
          plugin
              ? 'plugin'
              : market
                  ? 'marketplace'
                  : action == 'chat.complete'
                      ? 'model'
                      : 'endpoint',
          ref)
      : _invalid();
}

String _tool(String action, Map<String, Object?> value) =>
    action == 'plugin.call' && value['tool'] is String
        ? value['tool'] as String
        : action;

List<String> _scopes(String action, Map<String, Object?> value) {
  final selected = <String>{};
  if (const {'chat.complete', 'agent.run', 'workflow.run'}.contains(action)) {
    selected.add('network');
  }
  if (action == 'plugin.call') {
    selected.addAll(const ['write', 'exec', 'network', 'plugin']);
  } else if (action == 'plugin.probe') {
    selected.addAll(const ['exec', 'network', 'plugin']);
  } else if (action.startsWith('plugin.') ||
      action.startsWith('marketplace.')) {
    selected.addAll(const ['write', 'plugin']);
  }
  if (const {'agent.run', 'workflow.run'}.contains(action)) {
    if (value['allow_write'] == true) {
      selected.add('write');
    }
    if (value['allow_exec'] == true) {
      selected.add('exec');
    }
  }
  if ((value['credential_refs'] as List).isNotEmpty) {
    selected.add('secrets');
  }
  return const ['write', 'exec', 'network', 'plugin', 'secrets']
      .where(selected.contains)
      .toList();
}
