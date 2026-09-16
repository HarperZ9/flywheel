part of 'gateway_agent_execution_review.dart';

final _mcpServerId = RegExp(r'^[a-z][a-z0-9_]{0,23}$');
final _mcpCatalogRef = RegExp(r'^[a-z][A-Za-z0-9_.-]{0,63}$');
final _mcpRuntimeTool = RegExp(r'^mcp_[a-z0-9_]{1,24}__[a-z0-9_]{1,28}$');
final _mcpEnvSlot = RegExp(r'^[A-Z][A-Z0-9_]{0,127}$');

final class GatewayAgentMcpAdmissionReview extends DefensiveModel {
  final String admissionSha256;
  final List<GatewayAgentMcpServerReview> servers;
  GatewayAgentMcpAdmissionReview._(
      this.admissionSha256, this.servers, super.parseIssues);

  factory GatewayAgentMcpAdmissionReview.fromRaw(Object? raw, String field) {
    if (raw is Map<String, Object?>) {
      return GatewayAgentMcpAdmissionReview.fromJson(raw, field);
    }
    return GatewayAgentMcpAdmissionReview._(
        '', const [], [(field: field, rawValue: safeRawValue(raw))]);
  }

  factory GatewayAgentMcpAdmissionReview.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    _exactFields(
        json, const {'schema', 'admission_sha256', 'servers'}, issues, field);
    expectSchema(json, gatewayAgentMcpAdmissionReviewSchema, issues);
    final servers = readRecords<GatewayAgentMcpServerReview>(json['servers'],
        '$field.servers', issues, GatewayAgentMcpServerReview.fromJson);
    issues.addAll(servers.expand((server) => server.parseIssues));
    if (servers.isEmpty) {
      addParseIssue(issues, '$field.servers', json['servers']);
    }
    final names = runtimeToolNamesFromServers(servers);
    if (names.toSet().length != names.length) {
      addParseIssue(issues, '$field.servers.runtime_tool_name', names);
    }
    return GatewayAgentMcpAdmissionReview._(
        readText(json, 'admission_sha256', issues, pattern: sha256Pattern),
        servers,
        issues);
  }

  List<String> get runtimeToolNames => runtimeToolNamesFromServers(servers);
  String get serverLabel => servers.isEmpty
      ? 'none'
      : '${servers.length} catalog server${servers.length == 1 ? '' : 's'}';
  String get toolNamesLabel =>
      runtimeToolNames.isEmpty ? 'none' : runtimeToolNames.join(', ');

  void validateCapabilities(GatewayAgentExecutionCapabilities capabilities,
      String field, List<ParseIssue> issues) {
    if (!capabilities.allowMcp) {
      addParseIssue(issues, '$field.capabilities.allow_mcp', false);
    }
  }
}

List<String> runtimeToolNamesFromServers(
        List<GatewayAgentMcpServerReview> servers) =>
    [for (final server in servers) ...server.runtimeToolNames];

final class GatewayAgentMcpServerReview extends DefensiveModel {
  final String serverId, catalogRef, descriptorSha256, configSha256;
  final String toolsListSha256;
  final String? discoveryReceiptSha256, cacheScopeSha256;
  final int timeoutSeconds;
  final GatewayAgentMcpLaunchReview launch;
  final List<GatewayAgentMcpToolReview> tools;
  GatewayAgentMcpServerReview._(
      this.serverId,
      this.catalogRef,
      this.timeoutSeconds,
      this.descriptorSha256,
      this.configSha256,
      this.toolsListSha256,
      this.discoveryReceiptSha256,
      this.cacheScopeSha256,
      this.launch,
      this.tools,
      super.parseIssues);

  factory GatewayAgentMcpServerReview.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    _exactFields(
        json,
        const {
          'server_id',
          'catalog_ref',
          'timeout_s',
          'descriptor_sha256',
          'config_sha256',
          'tools_list_sha256',
          'discovery_receipt_sha256',
          'cache_scope_sha256',
          'launch',
          'tools',
        },
        issues,
        field);
    final launch =
        GatewayAgentMcpLaunchReview.fromRaw(json['launch'], '$field.launch');
    final tools = readRecords<GatewayAgentMcpToolReview>(json['tools'],
        '$field.tools', issues, GatewayAgentMcpToolReview.fromJson);
    issues
      ..addAll(launch.parseIssues)
      ..addAll(tools.expand((tool) => tool.parseIssues));
    if (tools.isEmpty) addParseIssue(issues, '$field.tools', json['tools']);
    return GatewayAgentMcpServerReview._(
        readText(json, 'server_id', issues, pattern: _mcpServerId),
        readText(json, 'catalog_ref', issues, pattern: _mcpCatalogRef),
        _readInt(json, 'timeout_s', 1, 60, issues),
        readText(json, 'descriptor_sha256', issues, pattern: sha256Pattern),
        readText(json, 'config_sha256', issues, pattern: sha256Pattern),
        readText(json, 'tools_list_sha256', issues, pattern: sha256Pattern),
        _readNullableSha256(json, 'discovery_receipt_sha256', issues),
        _readNullableSha256(json, 'cache_scope_sha256', issues),
        launch,
        tools,
        issues);
  }

  List<String> get runtimeToolNames =>
      [for (final tool in tools) tool.runtimeToolName];
  String get toolsLabel =>
      runtimeToolNames.isEmpty ? 'none' : runtimeToolNames.join(', ');
  String get limitsLabel => tools.isEmpty
      ? 'none'
      : tools
          .map((tool) => '${tool.runtimeToolName}: ${tool.limits.label}')
          .join('; ');
  String get doesNotProveLabel {
    final values = <String>{
      for (final tool in tools) ...tool.doesNotProve,
    };
    return values.isEmpty ? 'none' : values.join('; ');
  }
}

final class GatewayAgentMcpLaunchReview extends DefensiveModel {
  final String transport;
  final bool inheritEnv, urlSelected, hideWindow;
  final List<String> envOverrideKeys, allowedTools;
  GatewayAgentMcpLaunchReview._(
      this.transport,
      this.inheritEnv,
      this.urlSelected,
      this.hideWindow,
      this.envOverrideKeys,
      this.allowedTools,
      super.parseIssues);

  factory GatewayAgentMcpLaunchReview.fromRaw(Object? raw, String field) {
    if (raw is! Map<String, Object?>) {
      return GatewayAgentMcpLaunchReview._('', false, false, false, const [],
          const [], [(field: field, rawValue: safeRawValue(raw))]);
    }
    final issues = <ParseIssue>[];
    _exactFields(
        raw,
        const {
          'transport',
          'inherit_env',
          'url_selected',
          'hide_window',
          'env_override_keys',
          'allowed_tools',
        },
        issues,
        field);
    final envKeys = readStringList(
        raw['env_override_keys'], '$field.env_override_keys', issues);
    final allowedTools = readStringList(
        raw['allowed_tools'], '$field.allowed_tools', issues);
    if (envKeys.any((key) => !_mcpEnvSlot.hasMatch(key))) {
      addParseIssue(issues, '$field.env_override_keys', envKeys);
    }
    final inherit = _readBool(raw, 'inherit_env', issues);
    if (inherit) addParseIssue(issues, '$field.inherit_env', inherit);
    return GatewayAgentMcpLaunchReview._(
        _readChoice(raw, 'transport', const {'catalog', 'stdio'}, issues),
        inherit,
        _readBool(raw, 'url_selected', issues),
        _readBool(raw, 'hide_window', issues),
        envKeys,
        allowedTools,
        issues);
  }
}

final class GatewayAgentMcpToolReview extends DefensiveModel {
  final String sourceToolName, runtimeToolName, inputSchemaSha256,
      descriptorSha256, authoritySource;
  final GatewayAgentMcpAuthority declaredAuthority;
  final GatewayAgentMcpLimits limits;
  final List<String> doesNotProve;
  GatewayAgentMcpToolReview._(
      this.sourceToolName,
      this.runtimeToolName,
      this.inputSchemaSha256,
      this.descriptorSha256,
      this.authoritySource,
      this.declaredAuthority,
      this.limits,
      this.doesNotProve,
      super.parseIssues);

  factory GatewayAgentMcpToolReview.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    _exactFields(
        json,
        const {
          'source_tool_name',
          'runtime_tool_name',
          'input_schema_sha256',
          'descriptor_sha256',
          'declared_authority',
          'authority_source',
          'enforced_limits',
          'does_not_prove'
        },
        issues,
        field);
    final authority = GatewayAgentMcpAuthority.fromRaw(
        json['declared_authority'], '$field.declared_authority');
    final limits = GatewayAgentMcpLimits.fromRaw(
        json['enforced_limits'], '$field.enforced_limits');
    final doesNotProve =
        readStringList(json['does_not_prove'], '$field.does_not_prove', issues);
    if (doesNotProve.isEmpty) {
      addParseIssue(issues, '$field.does_not_prove', json['does_not_prove']);
    }
    issues
      ..addAll(authority.parseIssues)
      ..addAll(limits.parseIssues);
    return GatewayAgentMcpToolReview._(
        _readMcpSource(json, 'source_tool_name', issues),
        readText(json, 'runtime_tool_name', issues, pattern: _mcpRuntimeTool),
        readText(json, 'input_schema_sha256', issues, pattern: sha256Pattern),
        readText(json, 'descriptor_sha256', issues, pattern: sha256Pattern),
        readText(json, 'authority_source', issues),
        authority,
        limits,
        doesNotProve,
        issues);
  }
}
