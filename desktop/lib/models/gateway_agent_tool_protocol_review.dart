part of 'gateway_agent_execution_review.dart';

final class GatewayAgentToolProtocol extends DefensiveModel {
  final String protocol, resultOrderPolicy;
  final String? nativeApiRoute, toolSchemaSha256;
  final List<String> toolNames;
  final bool strictSchemas, parallelToolCalls;

  GatewayAgentToolProtocol._(
      this.protocol,
      this.nativeApiRoute,
      this.toolSchemaSha256,
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
    _exactFields(
        json,
        const {
          'schema',
          'protocol',
          'native_api_route',
          'tool_schema_sha256',
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
    return GatewayAgentToolProtocol._(
        protocol, route, digest, names, strict, parallel, order, issues);
  }

  String get protocolLabel => protocol == 'native'
      ? 'native / ${nativeApiRoute ?? 'unknown route'}'
      : protocol == 'text'
          ? 'text tool loop'
          : 'unknown protocol';

  String get toolSchemaDigestLabel => toolSchemaSha256 ?? 'none';

  String get toolNamesLabel =>
      toolNames.isEmpty ? 'none' : toolNames.join(', ');

  void validateCapabilities(GatewayAgentExecutionCapabilities capabilities,
      String field, List<ParseIssue> issues) {
    if (protocol != 'native') return;
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
    if (!_sameStrings(toolNames, expected)) {
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
  if (route == null || !nativeRoutes.contains(route)) {
    addParseIssue(issues, '$field.native_api_route', json['native_api_route']);
  }
  if (digest == null) {
    addParseIssue(
        issues, '$field.tool_schema_sha256', json['tool_schema_sha256']);
  }
  if (!allowedNameSets.contains(names.join('|'))) {
    addParseIssue(issues, '$field.tool_names', json['tool_names']);
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
  if (names.isNotEmpty) {
    addParseIssue(issues, '$field.tool_names', json['tool_names']);
  }
  if (strict) addParseIssue(issues, '$field.strict_schemas', strict);
  if (parallel) addParseIssue(issues, '$field.parallel_tool_calls', parallel);
  if (order != 'text_tool_loop') {
    addParseIssue(issues, '$field.result_order_policy', order);
  }
}
