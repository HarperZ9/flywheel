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
        'Run an owned official CLI session (claude-cli or codex). CLI auth stays with the vendor CLI and output tokens are unsupported.',
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

const nativeCliEndpoints = {'claude-cli', 'codex'};

bool agentExecutionModeSupportsEndpoint(
  AgentExecutionMode mode,
  String? endpoint,
) =>
    !mode.isNativeCli || nativeCliEndpoints.contains(endpoint);
