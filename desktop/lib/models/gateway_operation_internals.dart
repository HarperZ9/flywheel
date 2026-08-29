// Library-private derivation and validation helpers for GatewayOperation.
// Split from gateway_grant_models.dart to hold that file under the size gate;
// these stay a `part` so they keep library-scope access to _invalid, the
// reference patterns, and the parent library's imports. No public API changes.

part of 'gateway_grant_models.dart';

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
  if (action == 'operation.cancel') {
    final ref = value['operation_ref'];
    return ref is String ? GatewayDestination('operation', ref) : _invalid();
  }
  if (action == 'companion.ask') {
    return const GatewayDestination('model', 'companion');
  }
  if (action == 'forge.create') {
    return const GatewayDestination('forge', 'forge');
  }
  if (action == 'forge.recheck') {
    final ref = value['prp_id'];
    return ref is String ? GatewayDestination('forge', ref) : _invalid();
  }
  if (action == 'embeddings.create') {
    final ref = value['model'];
    return GatewayDestination(
        'model', ref is String && ref.isNotEmpty ? ref : 'embeddings');
  }
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
  if (action == 'operation.cancel') return const ['exec'];
  final selected = <String>{};
  if (const {
        'chat.complete',
        'agent.run',
        'workflow.run',
        'plan.run',
        'companion.ask',
        'route.send',
        'forge.create',
        'forge.recheck',
        'embeddings.create',
      }.contains(action)) {
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
  if (const {'agent.run', 'workflow.run', 'plan.run'}.contains(action)) {
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

void _validateCancel(Map<String, Object?> value) {
  const fields = {
    'operation_ref',
    'timeout_ms',
    'data_refs',
    'credential_refs'
  };
  final reference = value['operation_ref'];
  final timeout = value['timeout_ms'];
  if (value.keys.toSet().length != fields.length ||
      !value.keys.every(fields.contains) ||
      reference is! String ||
      !operationRefPattern.hasMatch(reference) ||
      timeout is! int ||
      timeout < 1 ||
      timeout > 30000 ||
      (value['data_refs'] as List).isNotEmpty ||
      (value['credential_refs'] as List).isNotEmpty) {
    _invalid();
  }
}
