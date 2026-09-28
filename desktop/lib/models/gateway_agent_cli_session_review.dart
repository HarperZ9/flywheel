part of 'gateway_agent_execution_review.dart';

final class GatewayAgentCliSession extends DefensiveModel {
  final String provider, profile, filesystemScope, authMode, version;
  final List<String> tools, limitations;
  final GatewayAgentCliControls controls;

  GatewayAgentCliSession._(
      this.provider,
      this.profile,
      this.tools,
      this.filesystemScope,
      this.authMode,
      this.controls,
      this.limitations,
      this.version,
      super.parseIssues);

  factory GatewayAgentCliSession.fromRaw(Object? raw, String field) {
    if (raw is Map<String, Object?>) {
      return GatewayAgentCliSession.fromJson(raw, field);
    }
    return GatewayAgentCliSession._(
        '',
        '',
        const [],
        '',
        '',
        GatewayAgentCliControls.empty,
        const [],
        '',
        [
          (field: field, rawValue: safeRawValue(raw)),
        ]);
  }

  factory GatewayAgentCliSession.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    _exactFields(
        json,
        const {
          'provider',
          'profile',
          'tools',
          'filesystem_scope',
          'auth_mode',
          'controls',
          'limitations',
          'version',
        },
        issues,
        field);
    final controls =
        GatewayAgentCliControls.fromRaw(json['controls'], '$field.controls');
    issues.addAll(controls.parseIssues);
    return GatewayAgentCliSession._(
        _readChoice(json, 'provider', const {'claude-cli'}, issues),
        _readChoice(
            json, 'profile', const {'claude_restricted_files_v1'}, issues),
        readStringList(json['tools'], '$field.tools', issues),
        _readChoice(
            json,
            'filesystem_scope',
            const {
              'working_directory_file_tools',
              'os_read_scope_workspace_write_only',
            },
            issues),
        _readChoice(json, 'auth_mode', const {'official_cli_own_auth'}, issues),
        controls,
        readStringList(json['limitations'], '$field.limitations', issues),
        readText(json, 'version', issues, pattern: RegExp(r'^\d+\.\d+\.\d+$')),
        issues);
  }

  String get engineLabel => '$provider / $version';

  String get authLabel => authMode == 'official_cli_own_auth'
      ? 'official CLI owns authentication'
      : 'unknown CLI authentication';

  String get boundsLabel =>
      'process deadline; steps ${_controlLabel(controls.maxSteps)}; '
      'tokens ${_controlLabel(controls.maxTokens)}; '
      'seed ${_controlLabel(controls.seed)}';

  String get filesystemScopeLabel =>
      filesystemScope == 'working_directory_file_tools'
          ? 'working directory file tools'
          : filesystemScope == 'os_read_scope_workspace_write_only'
              ? 'OS read scope, workspace writes only'
              : 'unknown filesystem scope';

  String get providerPolicyLabel =>
      limitations.contains('PROVIDER_POLICY_APPLIES')
          ? 'provider policy applies; hooks may be provider-managed'
          : 'provider policy unknown';

  String get reasoningEvidenceLabel =>
      limitations.contains('HIDDEN_REASONING_UNAVAILABLE')
          ? 'hidden reasoning unavailable; Claude reasoning not retained'
          : 'reasoning evidence unknown';

  String get toolsLabel => tools.isEmpty ? 'none' : tools.join(', ');

  String get limitationsLabel =>
      limitations.isEmpty ? 'none' : limitations.join(', ');

  void validateReview({
    required Object? endpoint,
    required GatewayAgentExecutionCapabilities capabilities,
    required String field,
    required List<ParseIssue> issues,
  }) {
    if (provider != endpoint) {
      addParseIssue(issues, '$field.provider', provider);
    }
    if (capabilities.allowMcp) {
      addParseIssue(issues, '$field.capabilities.allow_mcp', true);
    }
    final expectedTools = _expectedTools(capabilities);
    if (!_sameStrings(tools, expectedTools)) {
      addParseIssue(issues, '$field.tools', tools);
    }
    if (profile != _expectedProfile) {
      addParseIssue(issues, '$field.profile', profile);
    }
    if (filesystemScope != _expectedFilesystemScope) {
      addParseIssue(issues, '$field.filesystem_scope', filesystemScope);
    }
    const expectedStepControl = 'native_turn_limit';
    if (controls.timeoutSeconds != 'owned_process_deadline') {
      addParseIssue(
          issues, '$field.controls.timeout_s', controls.timeoutSeconds);
    }
    if (controls.maxSteps != expectedStepControl) {
      addParseIssue(issues, '$field.controls.max_steps', controls.maxSteps);
    }
    if (controls.maxTokens != 'unsupported') {
      addParseIssue(issues, '$field.controls.max_tokens', controls.maxTokens);
    }
    if (controls.seed != 'unsupported') {
      addParseIssue(issues, '$field.controls.seed', controls.seed);
    }
    if (!_sameStrings(limitations, _expectedLimitations)) {
      addParseIssue(issues, '$field.limitations', limitations);
    }
    if (provider == 'claude-cli' && capabilities.allowExec) {
      addParseIssue(issues, '$field.capabilities.allow_exec', true);
    }
  }

  List<String> _expectedTools(GatewayAgentExecutionCapabilities capabilities) {
    if (provider == 'claude-cli') {
      return [
        'Read',
        'Glob',
        'Grep',
        if (capabilities.allowWrite) ...['Edit', 'Write'],
      ];
    }
    return const [];
  }

  String get _expectedProfile =>
      provider == 'claude-cli' ? 'claude_restricted_files_v1' : '';

  String get _expectedFilesystemScope =>
      provider == 'claude-cli' ? 'working_directory_file_tools' : '';

  List<String> get _expectedLimitations => [
        'NO_OS_ADMINISTRATION',
        'NO_PROVIDER_RESUME',
        'PROVIDER_POLICY_APPLIES',
        'NO_HARD_TOKEN_LIMIT',
        'HIDDEN_REASONING_UNAVAILABLE',
        'CLAUDE_REASONING_NOT_RETAINED',
      ];
}

final class GatewayAgentCliControls extends DefensiveModel {
  final String timeoutSeconds, maxSteps, maxTokens, seed;
  static final empty = GatewayAgentCliControls._('', '', '', '', const []);
  GatewayAgentCliControls._(this.timeoutSeconds, this.maxSteps, this.maxTokens,
      this.seed, super.parseIssues);

  factory GatewayAgentCliControls.fromRaw(Object? raw, String field) {
    if (raw is! Map<String, Object?>) {
      return GatewayAgentCliControls._('', '', '', '', [
        (field: field, rawValue: safeRawValue(raw)),
      ]);
    }
    final issues = <ParseIssue>[];
    _exactFields(raw, const {'timeout_s', 'max_steps', 'max_tokens', 'seed'},
        issues, field);
    return GatewayAgentCliControls._(
        _readChoice(raw, 'timeout_s', const {'owned_process_deadline'}, issues),
        _readChoice(raw, 'max_steps',
            const {'native_turn_limit', 'unsupported'}, issues),
        _readChoice(raw, 'max_tokens', const {'unsupported'}, issues),
        _readChoice(raw, 'seed', const {'unsupported'}, issues),
        issues);
  }
}

String _controlLabel(String value) => value == 'owned_process_deadline'
    ? 'process deadline'
    : value == 'native_turn_limit'
        ? 'native turn limit'
        : value == 'unsupported'
            ? 'unsupported'
            : 'unknown';
