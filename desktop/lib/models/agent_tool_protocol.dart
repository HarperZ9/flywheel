enum AgentToolProtocol {
  compatibility(null, 'compatibility',
      'Use the endpoint default tool transport. The operation omits tool_protocol.'),
  native('native', 'native',
      'Request provider-native tool calls. Unsupported endpoints reject this.');

  final String? wire;
  final String label, help;
  const AgentToolProtocol(this.wire, this.label, this.help);
}
