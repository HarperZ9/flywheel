part of 'gateway_agent_execution_review.dart';

final class GatewayAgentMcpAuthority extends DefensiveModel {
  final bool read, write, execute, critical, network;
  GatewayAgentMcpAuthority._(this.read, this.write, this.execute, this.critical,
      this.network, super.parseIssues);
  factory GatewayAgentMcpAuthority.fromRaw(Object? raw, String field) {
    if (raw is! Map<String, Object?>) {
      return GatewayAgentMcpAuthority._(false, false, false, false, false,
          [(field: field, rawValue: safeRawValue(raw))]);
    }
    final issues = <ParseIssue>[];
    _exactFields(raw, const {'read', 'write', 'execute', 'critical', 'network'},
        issues, field);
    return GatewayAgentMcpAuthority._(
        _readBool(raw, 'read', issues),
        _readBool(raw, 'write', issues),
        _readBool(raw, 'execute', issues),
        _readBool(raw, 'critical', issues),
        _readBool(raw, 'network', issues),
        issues);
  }
}

final class GatewayAgentMcpLimits extends DefensiveModel {
  final bool noShell, pinnedCwd, inheritEnv, networkSandbox, filesystemSandbox;
  GatewayAgentMcpLimits._(this.noShell, this.pinnedCwd, this.inheritEnv,
      this.networkSandbox, this.filesystemSandbox, super.parseIssues);
  factory GatewayAgentMcpLimits.fromRaw(Object? raw, String field) {
    if (raw is! Map<String, Object?>) {
      return GatewayAgentMcpLimits._(false, false, false, false, false,
          [(field: field, rawValue: safeRawValue(raw))]);
    }
    final issues = <ParseIssue>[];
    _exactFields(
        raw,
        const {
          'no_shell',
          'pinned_cwd',
          'inherit_env',
          'network_sandbox',
          'filesystem_sandbox'
        },
        issues,
        field);
    final noShell = _readBool(raw, 'no_shell', issues);
    final pinnedCwd = _readBool(raw, 'pinned_cwd', issues);
    final inheritEnv = _readBool(raw, 'inherit_env', issues);
    final networkSandbox = _readBool(raw, 'network_sandbox', issues);
    final filesystemSandbox = _readBool(raw, 'filesystem_sandbox', issues);
    if (!noShell) addParseIssue(issues, '$field.no_shell', noShell);
    if (!pinnedCwd) addParseIssue(issues, '$field.pinned_cwd', pinnedCwd);
    if (inheritEnv) addParseIssue(issues, '$field.inherit_env', inheritEnv);
    if (networkSandbox) {
      addParseIssue(issues, '$field.network_sandbox', networkSandbox);
    }
    if (filesystemSandbox) {
      addParseIssue(issues, '$field.filesystem_sandbox', filesystemSandbox);
    }
    return GatewayAgentMcpLimits._(noShell, pinnedCwd, inheritEnv,
        networkSandbox, filesystemSandbox, issues);
  }

  String get label =>
      'no shell ${noShell ? 'yes' : 'no'} / cwd pinned ${pinnedCwd ? 'yes' : 'no'} / '
      'ambient env ${inheritEnv ? 'on' : 'off'} / network sandbox ${networkSandbox ? 'yes' : 'no'} / '
      'filesystem sandbox ${filesystemSandbox ? 'yes' : 'no'}';
}

String _readMcpSource(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is String &&
      raw.isNotEmpty &&
      raw.length <= 128 &&
      !raw.codeUnits.any((unit) => unit <= 0x20 || unit == 0x7f) &&
      isSafePublicText(raw)) {
    return raw;
  }
  addParseIssue(issues, field, raw);
  return '';
}
