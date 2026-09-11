part of 'gateway_agent_execution_review.dart';

// Tool-protocol authority lives in its own part so each review model file stays
// under the desktop source gate.

final class GatewayAgentExecutionModel extends DefensiveModel {
  final String? requestedModelReference;
  final String modelId, selection, observationPolicy;
  final GatewayAgentModelProfile? profile;

  static final empty =
      GatewayAgentExecutionModel._(null, '', '', '', null, const []);

  GatewayAgentExecutionModel._(this.requestedModelReference, this.modelId,
      this.selection, this.observationPolicy, this.profile, super.parseIssues);

  factory GatewayAgentExecutionModel.fromRaw(Object? raw, String field) {
    if (raw is Map<String, Object?>) {
      return GatewayAgentExecutionModel.fromJson(raw, field);
    }
    return GatewayAgentExecutionModel._(
        null, '', '', '', null, [(field: field, rawValue: safeRawValue(raw))]);
  }

  factory GatewayAgentExecutionModel.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    _exactFields(
        json,
        const {
          'requested_model_reference',
          'model_id',
          'selection',
          'observation_policy',
          'profile',
        },
        issues,
        field);
    final profile = _profile(json['profile'], '$field.profile', issues);
    return GatewayAgentExecutionModel._(
        _readNullableModelReference(json, 'requested_model_reference', issues),
        _readModelReference(json, 'model_id', issues),
        _readChoice(
            json, 'selection', const {'explicit', 'frozen_default'}, issues),
        _readChoice(json, 'observation_policy',
            const {'ollama_exact', 'provider_reported', 'unavailable'}, issues),
        profile,
        issues);
  }

  String get requestedLabel => requestedModelReference ?? 'endpoint default';
  String get selectionLabel => selection == 'explicit'
      ? 'explicit request'
      : selection == 'frozen_default'
          ? 'frozen endpoint default'
          : 'unknown selection';
  String get observationPolicyLabel => observationPolicy == 'ollama_exact'
      ? 'Ollama exact check during run'
      : observationPolicy == 'provider_reported'
          ? 'provider-reported string during run'
          : observationPolicy == 'unavailable'
              ? 'unavailable until run'
              : 'unknown observation basis';
}

final class GatewayAgentModelProfile extends DefensiveModel {
  final String profile, expectedManifestSha256, expectedArtifactSha256;
  GatewayAgentModelProfile._(this.profile, this.expectedManifestSha256,
      this.expectedArtifactSha256, super.parseIssues);

  factory GatewayAgentModelProfile.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    _exactFields(
        json,
        const {
          'profile',
          'expected_manifest_sha256',
          'expected_artifact_sha256',
        },
        issues,
        field);
    return GatewayAgentModelProfile._(
        readText(json, 'profile', issues),
        readText(json, 'expected_manifest_sha256', issues,
            pattern: sha256Pattern),
        readText(json, 'expected_artifact_sha256', issues,
            pattern: sha256Pattern),
        issues);
  }
}

GatewayAgentModelProfile? _profile(
    Object? raw, String field, List<ParseIssue> issues) {
  if (raw == null) return null;
  if (raw is! Map<String, Object?>) {
    addParseIssue(issues, field, raw);
    return null;
  }
  final profile = GatewayAgentModelProfile.fromJson(raw, field);
  issues.addAll(profile.parseIssues);
  return profile;
}

final class GatewayAgentExecutionBudget extends DefensiveModel {
  final int maxSteps, maxTokens, timeoutSeconds;
  static final empty = GatewayAgentExecutionBudget._(0, 0, 0, const []);
  GatewayAgentExecutionBudget._(
      this.maxSteps, this.maxTokens, this.timeoutSeconds, super.parseIssues);

  factory GatewayAgentExecutionBudget.fromRaw(Object? raw, String field) {
    if (raw is! Map<String, Object?>) {
      return GatewayAgentExecutionBudget._(
          0, 0, 0, [(field: field, rawValue: safeRawValue(raw))]);
    }
    final issues = <ParseIssue>[];
    _exactFields(
        raw, const {'max_steps', 'max_tokens', 'timeout_s'}, issues, field);
    return GatewayAgentExecutionBudget._(
        _readInt(raw, 'max_steps', 1, 12, issues),
        _readInt(raw, 'max_tokens', 1, 32768, issues),
        _readInt(raw, 'timeout_s', 1, 1800, issues),
        issues);
  }

  String get label =>
      '$maxSteps steps / $maxTokens output tokens / ${timeoutSeconds}s';
}

final class GatewayAgentExecutionCapabilities extends DefensiveModel {
  final bool allowWrite, allowExec, allowMcp;
  static final empty =
      GatewayAgentExecutionCapabilities._(false, false, false, const []);
  GatewayAgentExecutionCapabilities._(
      this.allowWrite, this.allowExec, this.allowMcp, super.parseIssues);

  factory GatewayAgentExecutionCapabilities.fromRaw(Object? raw, String field) {
    if (raw is! Map<String, Object?>) {
      return GatewayAgentExecutionCapabilities._(
          false, false, false, [(field: field, rawValue: safeRawValue(raw))]);
    }
    final issues = <ParseIssue>[];
    _exactFields(
        raw, const {'allow_write', 'allow_exec', 'allow_mcp'}, issues, field);
    return GatewayAgentExecutionCapabilities._(
        _readBool(raw, 'allow_write', issues),
        _readBool(raw, 'allow_exec', issues),
        _readBool(raw, 'allow_mcp', issues),
        issues);
  }

  String get label =>
      'write ${allowWrite ? 'on' : 'off'} / exec ${allowExec ? 'on' : 'off'} / MCP ${allowMcp ? 'on' : 'off'}';
}
