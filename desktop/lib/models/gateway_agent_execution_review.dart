import 'evidence_state.dart';

part 'gateway_agent_execution_review_fields.dart';
part 'gateway_agent_tool_protocol_review.dart';
part 'gateway_agent_cli_session_review.dart';

const gatewayAgentReviewSchemaV1 = 'flywheel.gateway-agent-review/v1';
const gatewayAgentReviewSchemaV2 = 'flywheel.gateway-agent-review/v2';
const gatewayAgentReviewSchemaV3 = 'flywheel.gateway-agent-review/v3';
const gatewayAgentToolProtocolSchema =
    'flywheel.gateway-agent-tool-protocol/v1';
const gatewayAgentReviewSchema = gatewayAgentReviewSchemaV1;

final _modelReference = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}$');
final _toolName = RegExp(r'^[a-z][a-z0-9_]{0,63}$');
final _endpointSecret =
    RegExp(r'(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|'
        r'\bgh[pousr]_[A-Za-z0-9]{30,}\b|'
        r'\bsk-(?:live|proj|ant)[A-Za-z0-9_-]{10,}\b)');
final _endpointAssignedSecret = RegExp(
  r'\b(?:secret|password|passwd|api_key|access_key)\s*[:=]\s*'
  r'["\x27]?[A-Za-z0-9/+_-]{12,}',
  caseSensitive: false,
);

final _windowsAbsolutePath = RegExp(r'^[A-Za-z]:[\\/].+');
final _posixAbsolutePath = RegExp(r'^/(?!/).+');
final _uncAbsolutePath = RegExp(r'^(?:\\\\|//)[^\\/\s]+[\\/][^\\/\s]+.*');
final _uriScheme = RegExp(r'^[A-Za-z][A-Za-z0-9+.-]*:');

final class GatewayAgentExecutionReview extends DefensiveModel {
  final bool reprepareRequired;
  final String bindingSha256, endpoint, baseUrl, root, workspacePolicySha256;
  final GatewayAgentExecutionModel model;
  final GatewayAgentExecutionBudget budget;
  final GatewayAgentExecutionCapabilities capabilities;
  final GatewayAgentToolProtocol? toolProtocol;
  final String executionMode;
  final GatewayAgentCliSession? cliSession;

  GatewayAgentExecutionReview._(
      this.reprepareRequired,
      this.bindingSha256,
      this.endpoint,
      this.baseUrl,
      this.model,
      this.root,
      this.workspacePolicySha256,
      this.budget,
      this.capabilities,
      this.toolProtocol,
      this.executionMode,
      this.cliSession,
      super.parseIssues);

  factory GatewayAgentExecutionReview.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    if (json.keys.length == 1 && json['status'] == 'reprepare_required') {
      return GatewayAgentExecutionReview._(
          true,
          '',
          '',
          '',
          GatewayAgentExecutionModel.empty,
          '',
          '',
          GatewayAgentExecutionBudget.empty,
          GatewayAgentExecutionCapabilities.empty,
          null,
          '',
          null,
          issues);
    }
    final schema = json['schema'];
    final isV2 = schema == gatewayAgentReviewSchemaV2;
    final isV3 = schema == gatewayAgentReviewSchemaV3;
    _exactFields(
        json,
        {
          'schema',
          'binding_sha256',
          'endpoint',
          'base_url',
          'model',
          'root',
          'workspace_policy_sha256',
          'budget',
          'capabilities',
          if (isV2) 'tool_protocol',
          if (isV3) ...{'execution_mode', 'cli_session'},
        },
        issues,
        field);
    if (schema != gatewayAgentReviewSchemaV1 &&
        schema != gatewayAgentReviewSchemaV2 &&
        schema != gatewayAgentReviewSchemaV3) {
      addParseIssue(issues, 'schema', schema);
    }
    final model =
        GatewayAgentExecutionModel.fromRaw(json['model'], '$field.model');
    final budget = GatewayAgentExecutionBudget.fromRaw(
        json['budget'], '$field.budget',
        allowUnsupportedMaxTokens: isV3);
    final capabilities = GatewayAgentExecutionCapabilities.fromRaw(
        json['capabilities'], '$field.capabilities');
    final protocol = isV2
        ? GatewayAgentToolProtocol.fromRaw(
            json['tool_protocol'], '$field.tool_protocol')
        : null;
    final cliSession = isV3
        ? GatewayAgentCliSession.fromRaw(
            json['cli_session'], '$field.cli_session')
        : null;
    protocol?.validateCapabilities(
        capabilities, '$field.tool_protocol', issues);
    cliSession?.validateReview(
        endpoint: json['endpoint'],
        capabilities: capabilities,
        field: '$field.cli_session',
        issues: issues);
    issues
      ..addAll(model.parseIssues)
      ..addAll(budget.parseIssues)
      ..addAll(capabilities.parseIssues)
      ..addAll(protocol?.parseIssues ?? const [])
      ..addAll(cliSession?.parseIssues ?? const []);
    return GatewayAgentExecutionReview._(
        false,
        readText(json, 'binding_sha256', issues, pattern: sha256Pattern),
        readText(json, 'endpoint', issues),
        _readEndpointBaseUrl(json, 'base_url', issues, allowEmpty: isV3),
        model,
        _readLocalPath(json, 'root', issues),
        readText(json, 'workspace_policy_sha256', issues,
            pattern: sha256Pattern),
        budget,
        capabilities,
        protocol,
        _readChoice(json, 'execution_mode',
            isV3 ? const {'native_cli_session'} : const {}, issues,
            optional: !isV3),
        cliSession,
        issues);
  }
}

String _readChoice(Map<String, Object?> json, String field, Set<String> allowed,
    List<ParseIssue> issues,
    {bool optional = false}) {
  final raw = json[field];
  if (optional && raw == null) return '';
  if (raw is String && allowed.contains(raw)) return raw;
  addParseIssue(issues, field, raw);
  return '';
}

String _readModelReference(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is String &&
      raw.isNotEmpty &&
      _modelReference.hasMatch(raw) &&
      isSafePublicText(raw)) {
    return raw;
  }
  addParseIssue(issues, field, raw);
  return '';
}

String? _readNullableModelReference(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw == null) return null;
  if (raw is String &&
      raw.isNotEmpty &&
      _modelReference.hasMatch(raw) &&
      isSafePublicText(raw)) {
    return raw;
  }
  addParseIssue(issues, field, raw);
  return null;
}

String? _readNullableText(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw == null) return null;
  if (raw is String && raw.isNotEmpty && isSafePublicText(raw)) return raw;
  addParseIssue(issues, field, raw);
  return null;
}

String? _readNullableSha256(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw == null) return null;
  if (raw is String && sha256Pattern.hasMatch(raw)) return raw;
  addParseIssue(issues, field, raw);
  return null;
}

List<String> _readToolNames(
    Object? raw, String field, List<ParseIssue> issues) {
  final values = readStringList(raw, field, issues);
  if (values.any((value) => !_toolName.hasMatch(value)) ||
      values.toSet().length != values.length) {
    addParseIssue(issues, field, raw);
    return const [];
  }
  return values;
}

String _readEndpointBaseUrl(
    Map<String, Object?> json, String field, List<ParseIssue> issues,
    {bool allowEmpty = false}) {
  final raw = json[field];
  if (allowEmpty) {
    if (raw == '') return '';
    addParseIssue(issues, field, raw);
    return '';
  }
  final parsed = raw is String ? Uri.tryParse(raw) : null;
  if (raw is String &&
      raw.isNotEmpty &&
      raw.length <= 512 &&
      !_endpointSecret.hasMatch(raw) &&
      !_endpointAssignedSecret.hasMatch(raw) &&
      !raw.contains('\\') &&
      !raw.codeUnits.any((unit) => unit <= 0x20 || unit == 0x7f) &&
      parsed != null &&
      const {'http', 'https'}.contains(parsed.scheme) &&
      parsed.hasAuthority &&
      parsed.userInfo.isEmpty &&
      !parsed.hasQuery &&
      !parsed.hasFragment) {
    return raw;
  }
  addParseIssue(issues, field, raw);
  return '';
}

String _readLocalPath(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is String &&
      raw.isNotEmpty &&
      raw.length <= 512 &&
      !_isUriShapedPath(raw) &&
      _isAbsoluteLocalPath(raw) &&
      !raw.codeUnits.any((unit) => unit <= 0x1f || unit == 0x7f) &&
      isSafeLocalPath(raw)) {
    return raw;
  }
  addParseIssue(issues, field, raw);
  return '';
}

bool _isAbsoluteLocalPath(String value) =>
    _windowsAbsolutePath.hasMatch(value) ||
    _posixAbsolutePath.hasMatch(value) ||
    _uncAbsolutePath.hasMatch(value);

bool _isUriShapedPath(String value) =>
    _uriScheme.hasMatch(value) && !_windowsAbsolutePath.hasMatch(value);

int _readInt(Map<String, Object?> json, String field, int min, int max,
    List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is int && raw >= min && raw <= max) return raw;
  addParseIssue(issues, field, raw);
  return 0;
}

bool _readBool(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is bool) return raw;
  addParseIssue(issues, field, raw);
  return false;
}

void _exactFields(Map<String, Object?> value, Set<String> fields,
    List<ParseIssue> issues, String field) {
  if (value.keys.toSet().length != fields.length ||
      !value.keys.every(fields.contains)) {
    addParseIssue(issues, field, value.keys.toList());
  }
}
