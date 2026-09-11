enum AgentExecutionMode {
  api(
    label: 'API agent',
    help:
        'Use the gateway agent API path. Tool protocol and token budget controls apply here.',
  ),
  nativeCliSession(
    label: 'native CLI session',
    wire: 'native_cli_session',
    help:
        'Run an owned official CLI session. CLI auth stays with the CLI, output tokens are unsupported, and Codex CLI is unavailable.',
  );

  const AgentExecutionMode({
    required this.label,
    required this.help,
    this.wire,
  });

  final String label;
  final String help;
  final String? wire;

  bool get isNativeCli => this == AgentExecutionMode.nativeCliSession;

  static AgentExecutionMode fromWire(String? value) =>
      value == nativeCliSession.wire ? nativeCliSession : api;
}

bool agentExecutionModeSupportsEndpoint(
  AgentExecutionMode mode,
  String? endpoint,
) =>
    !mode.isNativeCli || endpoint == 'claude-cli';
