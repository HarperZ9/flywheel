import 'evidence_state.dart';

part 'gateway_agent_execution_review_fields.dart';
part 'gateway_agent_execution_review_parsing.dart';
part 'gateway_agent_tool_protocol_review.dart';
part 'gateway_agent_mcp_admission_review.dart';
part 'gateway_agent_mcp_limits_review.dart';
part 'gateway_agent_cli_session_review.dart';

const gatewayAgentReviewSchemaV1 = 'flywheel.gateway-agent-review/v1';
const gatewayAgentReviewSchemaV2 = 'flywheel.gateway-agent-review/v2';
const gatewayAgentReviewSchemaV3 = 'flywheel.gateway-agent-review/v3';
const gatewayAgentReviewSchemaV4 = 'flywheel.gateway-agent-review/v4';
const gatewayAgentToolProtocolSchema =
    'flywheel.gateway-agent-tool-protocol/v1';
const gatewayAgentMcpAdmissionReviewSchema =
    'flywheel.gateway-agent-mcp-admission-review/v1';
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
  final GatewayAgentMcpAdmissionReview? mcpAdmission;
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
      this.mcpAdmission,
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
          null,
          '',
          null,
          issues);
    }
    final schema = json['schema'];
    final isV2 = schema == gatewayAgentReviewSchemaV2;
    final isV3 = schema == gatewayAgentReviewSchemaV3;
    final isV4 = schema == gatewayAgentReviewSchemaV4;
    final hasToolProtocol = isV2 || (isV4 && json.containsKey('tool_protocol'));
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
          if (hasToolProtocol) 'tool_protocol',
          if (isV3) ...{'execution_mode', 'cli_session'},
          if (isV4) 'mcp_admission',
        },
        issues,
        field);
    if (schema != gatewayAgentReviewSchemaV1 &&
        schema != gatewayAgentReviewSchemaV2 &&
        schema != gatewayAgentReviewSchemaV3 &&
        schema != gatewayAgentReviewSchemaV4) {
      addParseIssue(issues, 'schema', schema);
    }
    final model =
        GatewayAgentExecutionModel.fromRaw(json['model'], '$field.model');
    final budget = GatewayAgentExecutionBudget.fromRaw(
        json['budget'], '$field.budget',
        allowUnsupportedMaxTokens: isV3);
    final capabilities = GatewayAgentExecutionCapabilities.fromRaw(
        json['capabilities'], '$field.capabilities');
    final protocol = hasToolProtocol
        ? GatewayAgentToolProtocol.fromRaw(
            json['tool_protocol'], '$field.tool_protocol')
        : null;
    final mcpAdmission = isV4
        ? GatewayAgentMcpAdmissionReview.fromRaw(
            json['mcp_admission'], '$field.mcp_admission')
        : null;
    final cliSession = isV3
        ? GatewayAgentCliSession.fromRaw(
            json['cli_session'], '$field.cli_session')
        : null;
    protocol?.validateCapabilities(
        capabilities, '$field.tool_protocol', issues);
    protocol?.validateMcpAdmission(
        mcpAdmission, '$field.tool_protocol', issues);
    mcpAdmission?.validateCapabilities(
        capabilities, '$field.mcp_admission', issues);
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
      ..addAll(mcpAdmission?.parseIssues ?? const [])
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
        mcpAdmission,
        _readChoice(json, 'execution_mode',
            isV3 ? const {'native_cli_session'} : const {}, issues,
            optional: !isV3),
        cliSession,
        issues);
  }
}
