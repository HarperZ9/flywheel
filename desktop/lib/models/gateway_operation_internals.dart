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

/// Destinations whose ref is a fixed name rather than a field of the
/// operation. These three tables mirror destination_for in
/// harness/gateway_operation_shape.py. The engine derives the authoritative
/// destination; a client that derived a different one would name the wrong
/// target in everything it renders before the sheet shows the engine's answer.
const _fixedDestinations = {
  'companion.ask': GatewayDestination('model', 'companion'),
  'forge.create': GatewayDestination('forge', 'forge'),
  'bench.run': GatewayDestination('bench', 'private-bench'),
  'invent.round': GatewayDestination('forge', 'conjecture-forge'),
  'lean.check': GatewayDestination('oracle', 'lean'),
  'infra.isolation': GatewayDestination('boundary', 'isolation'),
};

/// Destinations whose ref is one named field of the operation: (kind, field).
const _fieldDestinations = {
  'operation.cancel': ('operation', 'operation_ref'),
  'forge.recheck': ('forge', 'prp_id'),
  'suite.audit': ('suite', 'path'),
  'lane.call': ('lane', 'name'),
  'store.put': ('store', 'kind'),
  'import.config': ('workspace', 'root'),
};

/// Name the pack the operator is admitting, or say the manifest is unnamed
/// rather than inventing an identifier the admission may not carry.
String _packRef(Object? manifest) {
  if (manifest is! Map) return 'unnamed-pack';
  final id = manifest['pack_id'];
  final ref = id is String && id.isNotEmpty ? id : manifest['name'];
  return ref is String && ref.trim().isNotEmpty ? ref : 'unnamed-pack';
}

GatewayDestination _destination(String action, Map<String, Object?> value) {
  if (action == 'infra.credential_scan') {
    final root = value['root'];
    return GatewayDestination(
        'scan', root is String && root.isNotEmpty ? root : 'environment');
  }
  if (action == 'infra.kill') {
    final mode = value['mode'];
    return GatewayDestination('kill-switch',
        mode is String && mode.isNotEmpty ? mode : 'evidence-preserving');
  }
  final fixed = _fixedDestinations[action];
  if (fixed != null) return fixed;
  final named = _fieldDestinations[action];
  if (named != null) {
    final ref = value[named.$2];
    return ref is String ? GatewayDestination(named.$1, ref) : _invalid();
  }
  if (action == 'packs.admit') {
    return GatewayDestination('pack', _packRef(value['manifest']));
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

/// The engine reads the operation's own tool field wherever one exists, which
/// today means plugin.call and lane.call. Naming only the first left a lane
/// call proposing its action name where the engine proposes the lane tool.
String _tool(String action, Map<String, Object?> value) {
  final tool = value['tool'];
  return tool is String && tool.isNotEmpty ? tool : action;
}

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
  if (action == 'bench.run') {
    // Gates are subprocess commands: the benchmark is an execution.
    selected.addAll(const ['exec', 'network']);
  }
  if (action == 'capability.probe') selected.add('network');
  if (action == 'invent.round') {
    // The forge calls a model to propose and a kernel to judge.
    selected.addAll(const ['network', 'write']);
  }
  if (action == 'lean.check') {
    // The Lean kernel is a subprocess and the verdict is stored.
    selected.addAll(const ['exec', 'write']);
  }
  if (action == 'suite.audit') selected.add('exec');
  if (action == 'lane.call') {
    selected.addAll(const ['exec', 'network', 'plugin']);
  }
  if (const {'packs.admit', 'store.put', 'import.config'}.contains(action)) {
    selected.add('write');
  }
  // It reads the files and variables where credentials live. It records a
  // fingerprint and never a value, and the scope still says secrets.
  if (action == 'infra.credential_scan') selected.add('secrets');
  if (action == 'infra.isolation') selected.add('network');
  if (action == 'infra.kill') {
    // Isolate the network, revoke the credentials, end the process.
    selected.addAll(const ['exec', 'network', 'secrets']);
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
