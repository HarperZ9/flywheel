part of 'gateway_agent_execution_review.dart';

final class GatewayAgentToolProtocol extends DefensiveModel {
  final String protocol, resultOrderPolicy;
  final String? nativeApiRoute, toolSchemaSha256, mcpAdmissionSha256;
  final List<String> toolNames;
  final bool strictSchemas, parallelToolCalls;

  GatewayAgentToolProtocol._(
      this.protocol,
      this.nativeApiRoute,
      this.toolSchemaSha256,
      this.mcpAdmissionSha256,
      this.toolNames,
      this.strictSchemas,
      this.parallelToolCalls,
      this.resultOrderPolicy,
      super.parseIssues);

  factory GatewayAgentToolProtocol.fromRaw(Object? raw, String field) {
    if (raw is Map<String, Object?>) {
      return GatewayAgentToolProtocol.fromJson(raw, field);
    }
    return GatewayAgentToolProtocol._(
        '',
        null,
        null,
        null,
        const [],
        false,
        false,
        '',
        [
          (field: field, rawValue: safeRawValue(raw)),
        ]);
  }

  factory GatewayAgentToolProtocol.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    final hasMcpDigest = json.containsKey('mcp_admission_sha256');
    _exactFields(
        json,
        {
          'schema',
          'protocol',
          'native_api_route',
          'tool_schema_sha256',
          if (hasMcpDigest) 'mcp_admission_sha256',
          'tool_names',
          'strict_schemas',
          'parallel_tool_calls',
          'result_order_policy',
        },
        issues,
        field);
    expectSchema(json, gatewayAgentToolProtocolSchema, issues);
    final protocol =
        _readChoice(json, 'protocol', const {'native', 'text'}, issues);
    final route = _readNullableText(json, 'native_api_route', issues);
    final digest = _readNullableSha256(json, 'tool_schema_sha256', issues);
    final mcpDigest = _readNullableSha256(json, 'mcp_admission_sha256', issues);
    final names =
        _readToolNames(json['tool_names'], '$field.tool_names', issues);
    final strict = _readBool(json, 'strict_schemas', issues);
    final parallel = _readBool(json, 'parallel_tool_calls', issues);
    final order = _readChoice(json, 'result_order_policy',
        const {'provider_order_sequential', 'text_tool_loop'}, issues);

    if (protocol == 'native') {
      _validateNativeProtocol(
          json, route, digest, names, strict, parallel, order, issues, field);
    } else if (protocol == 'text') {
      _validateTextProtocol(
          json, route, digest, names, strict, parallel, order, issues, field);
    }
    return GatewayAgentToolProtocol._(protocol, route, digest, mcpDigest, names,
        strict, parallel, order, issues);
  }

  String get protocolLabel => protocol == 'native'
      ? 'native / ${nativeApiRoute ?? 'unknown route'}'
      : protocol == 'text'
          ? 'text tool loop'
          : 'unknown protocol';

  String get toolSchemaDigestLabel => toolSchemaSha256 ?? 'none';
  String get mcpAdmissionDigestLabel => mcpAdmissionSha256 ?? 'none';

  String get toolNamesLabel =>
      toolNames.isEmpty ? 'none' : toolNames.join(', ');

  void validateCapabilities(GatewayAgentExecutionCapabilities capabilities,
      String field, List<ParseIssue> issues) {
    if (protocol != 'native') return;
    final mcpNames =
        toolNames.where((name) => name.startsWith('mcp_')).toList();
    final builtinNames =
        toolNames.where((name) => !name.startsWith('mcp_')).toList();
    final expected = <String>[
      'read_file',
      'list_dir',
      'grep',
      if (capabilities.allowWrite) ...[
        'write_file',
        'edit_file',
        'apply_patch',
      ],
      if (capabilities.allowExec) 'run',
    ];
    if (!_sameStrings(builtinNames, expected)) {
      addParseIssue(issues, '$field.tool_names', toolNames);
    }
    if (mcpNames.isNotEmpty && !capabilities.allowMcp) {
      addParseIssue(issues, '$field.capabilities.allow_mcp', false);
    }
    if (mcpAdmissionSha256 != null && !capabilities.allowMcp) {
      addParseIssue(issues, '$field.mcp_admission_sha256', mcpAdmissionSha256);
    }
  }

  void validateMcpAdmission(GatewayAgentMcpAdmissionReview? admission,
      String field, List<ParseIssue> issues) {
    if (protocol != 'native') return;
    final mcpNames =
        toolNames.where((name) => name.startsWith('mcp_')).toList();
    if (admission == null) {
      if (mcpNames.isNotEmpty || mcpAdmissionSha256 != null) {
        addParseIssue(
            issues, '$field.mcp_admission_sha256', mcpAdmissionSha256);
      }
      return;
    }
    if (mcpAdmissionSha256 != admission.admissionSha256) {
      addParseIssue(issues, '$field.mcp_admission_sha256', mcpAdmissionSha256);
      return;
    }
    if (!_sameStrings(mcpNames, admission.runtimeToolNames)) {
      addParseIssue(issues, '$field.tool_names', toolNames);
    }
  }
}

bool _sameStrings(List<String> left, List<String> right) =>
    left.length == right.length &&
    left.indexed.every((entry) => entry.$2 == right[entry.$1]);

void _validateNativeProtocol(
  Map<String, Object?> json,
  String? route,
  String? digest,
  List<String> names,
  bool strict,
  bool parallel,
  String order,
  List<ParseIssue> issues,
  String field,
) {
  const nativeRoutes = {'openai_responses', 'anthropic_messages'};
  const allowedNameSets = {
    'read_file|list_dir|grep',
    'read_file|list_dir|grep|write_file|edit_file|apply_patch',
    'read_file|list_dir|grep|run',
    'read_file|list_dir|grep|write_file|edit_file|apply_patch|run',
  };
  final builtinNames = names.where((name) => !name.startsWith('mcp_')).toList();
  final mcpNames = names.where((name) => name.startsWith('mcp_')).toList();
  if (route == null || !nativeRoutes.contains(route)) {
    addParseIssue(issues, '$field.native_api_route', json['native_api_route']);
  }
  if (digest == null) {
    addParseIssue(
        issues, '$field.tool_schema_sha256', json['tool_schema_sha256']);
  }
  if (!allowedNameSets.contains(builtinNames.join('|'))) {
    addParseIssue(issues, '$field.tool_names', json['tool_names']);
  }
  if (mcpNames.isNotEmpty && json['mcp_admission_sha256'] == null) {
    addParseIssue(issues, '$field.mcp_admission_sha256', null);
  }
  if (!strict) addParseIssue(issues, '$field.strict_schemas', strict);
  if (parallel) addParseIssue(issues, '$field.parallel_tool_calls', parallel);
  if (order != 'provider_order_sequential') {
    addParseIssue(issues, '$field.result_order_policy', order);
  }
}

void _validateTextProtocol(
  Map<String, Object?> json,
  String? route,
  String? digest,
  List<String> names,
  bool strict,
  bool parallel,
  String order,
  List<ParseIssue> issues,
  String field,
) {
  if (route != null) {
    addParseIssue(issues, '$field.native_api_route', json['native_api_route']);
  }
  if (digest != null) {
    addParseIssue(
        issues, '$field.tool_schema_sha256', json['tool_schema_sha256']);
  }
  if (json['mcp_admission_sha256'] != null) {
    addParseIssue(
        issues, '$field.mcp_admission_sha256', json['mcp_admission_sha256']);
  }
  if (names.isNotEmpty) {
    addParseIssue(issues, '$field.tool_names', json['tool_names']);
  }
  if (strict) addParseIssue(issues, '$field.strict_schemas', strict);
  if (parallel) addParseIssue(issues, '$field.parallel_tool_calls', parallel);
  if (order != 'text_tool_loop') {
    addParseIssue(issues, '$field.result_order_policy', order);
  }
}
