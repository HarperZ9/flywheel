// endpoint_row.dart — the provider endpoint row and the ONE credential
// ranking every surface (Chat default, model picker, Endpoints roster)
// sorts by. Split from gateway_models.dart to hold the size gate; that file
// re-exports this one, so imports stay stable.

/// A provider endpoint row (GET /api/endpoints).
class EndpointRow {
  final String name;
  final String backend;
  final String kind;
  final bool local;
  final String credential; // present | absent | local-none | cli-auth
  final String providerRole;
  final bool configured;
  final String host;
  final String defaultModel;
  final bool receiptCapable;
  final String source;
  final bool accountRequired;
  final String accountState;
  final bool accountAuthenticated;

  EndpointRow({
    required this.name,
    required this.backend,
    String? kind,
    this.local = false,
    required this.credential,
    required this.providerRole,
    required this.configured,
    this.host = '',
    this.defaultModel = '',
    this.receiptCapable = true,
    this.source = '',
    this.accountRequired = false,
    this.accountState = '',
    this.accountAuthenticated = false,
  }) : kind = kind ?? backend;

  factory EndpointRow.fromJson(Map<String, dynamic> j) {
    String s(Object? v) => v == null ? '' : '$v';
    final name = s(j['name'] ?? j['model']);
    final kind = s(j['kind'] ?? j['backend']);
    final receiptCapable = j.containsKey('receipt_capable')
        ? j['receipt_capable'] == true
        : true;
    return EndpointRow(
      name: name,
      backend: s(j['backend'] ?? kind),
      kind: kind,
      local: j['local'] == true,
      credential: s(j['credential']).isEmpty ? 'absent' : s(j['credential']),
      providerRole: s(j['provider_role'] ?? j['providerRole']),
      configured: j.containsKey('configured')
          ? j['configured'] == true
          : receiptCapable,
      host: s(j['host']),
      defaultModel: s(j['default_model'] ?? j['defaultModel']),
      receiptCapable: receiptCapable,
      source: s(j['source']),
      accountRequired:
          j['account_required'] == true ||
          name == 'claude-cli' ||
          name == 'codex-cli',
      accountState: s(j['account_state']),
      accountAuthenticated: j['account_authenticated'] == true,
    );
  }

  bool get needsAccountAuth =>
      accountRequired || name == 'claude-cli' || name == 'codex-cli';
  bool get cliAuthenticated =>
      credential == 'cli-auth' && (!needsAccountAuth || accountAuthenticated);
  bool get hasCredential => credential == 'present' || cliAuthenticated;
  // The legacy wire label means a CLI was found, not that sign-in was checked.
  bool get cliPresent => credential == 'cli-auth';

  /// A row a first send can actually answer through: a signed-in
  /// subscription CLI, a present key, or a local tier.
  bool get usable =>
      receiptCapable &&
      (cliAuthenticated ||
          credential == 'present' ||
          credential == 'local-none');
}

/// The one credential ranking every surface sorts by: subscription tier
/// first (the paid-for CLI), then keyed/local, then unusable.
int endpointRank(EndpointRow e) => switch (e.credential) {
  'cli-auth' when e.cliAuthenticated => 0,
  'present' => 1,
  'local-none' => 1,
  'cli-auth' => 2,
  _ => 3,
};

/// The endpoint a fresh Chat should default to: the best USABLE row by
/// [endpointRank], or null when nothing on the roster can answer. Roster
/// order breaks ties, so the engine's own ordering still matters within a
/// tier. Never returns a keyless row -- a silent empty first send is worse
/// than an honest "no model".
EndpointRow? defaultEndpoint(List<EndpointRow> rows) {
  EndpointRow? best;
  var bestRank = 99;
  for (final r in rows) {
    if (!r.usable) continue;
    final rank = endpointRank(r);
    if (rank < bestRank) {
      best = r;
      bestRank = rank;
    }
  }
  return best;
}
