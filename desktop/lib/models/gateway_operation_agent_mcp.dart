part of 'gateway_grant_models.dart';

const _agentMcpAdmissionRequestSchema =
    'flywheel.agent-run-mcp-admission-request/v1';
final _agentMcpServerId = RegExp(r'^[a-z][a-z0-9_]{0,23}$');
final _agentMcpCatalogRef = RegExp(r'^[a-z][A-Za-z0-9_.-]{0,63}$');
final _agentMcpToolName = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,127}$');

void _validateAgentMcpAdmission(String action, Map<String, Object?> value) {
  if (!value.containsKey('mcp_admission')) return;
  if (action != 'agent.run' ||
      value['mcp_admission'] is! Map ||
      value['execution_mode'] == 'native_cli_session') {
    _invalid();
  }
  final admission = value['mcp_admission'] as Map;
  if (admission.keys.any((key) => key is! String) ||
      admission.keys.toSet().length != 2 ||
      admission['schema'] != _agentMcpAdmissionRequestSchema ||
      admission['servers'] is! List) {
    _invalid();
  }
  final servers = admission['servers'] as List;
  if (servers.isEmpty || servers.length > 8) _invalid();
  final serverKeys = <String>{};
  for (final rawServer in servers) {
    if (rawServer is! Map || rawServer.keys.any((key) => key is! String)) {
      _invalid();
    }
    final server = rawServer.cast<String, Object?>();
    const requiredFields = {
      'server_id',
      'catalog_ref',
      'receipt_sha256',
      'tools',
      'timeout_s',
    };
    const allowedFields = {...requiredFields, 'credential_refs'};
    if (!server.keys.every(allowedFields.contains) ||
        !requiredFields.every(server.containsKey)) {
      _invalid();
    }
    final serverId = server['server_id'];
    final catalogRef = server['catalog_ref'];
    final receipt = server['receipt_sha256'];
    final timeout = server['timeout_s'];
    final credentialRefs = server['credential_refs'];
    if (serverId is! String ||
        !_agentMcpServerId.hasMatch(serverId) ||
        catalogRef is! String ||
        !_agentMcpCatalogRef.hasMatch(catalogRef) ||
        receipt is! String ||
        !sha256Pattern.hasMatch(receipt) ||
        timeout is! int ||
        timeout < 1 ||
        timeout > 60 ||
        (credentialRefs != null &&
            (credentialRefs is! List || credentialRefs.isNotEmpty))) {
      _invalid();
    }
    final key = '$serverId\x1f$catalogRef\x1f$receipt';
    if (!serverKeys.add(key)) _invalid();
    final rawTools = server['tools'];
    if (rawTools is! List || rawTools.isEmpty || rawTools.length > 32) {
      _invalid();
    }
    final tools = <String>{};
    for (final rawTool in rawTools) {
      if (rawTool is! String ||
          !_agentMcpToolName.hasMatch(rawTool) ||
          !isSafePublicText(rawTool) ||
          !tools.add(rawTool)) {
        _invalid();
      }
    }
  }
}
