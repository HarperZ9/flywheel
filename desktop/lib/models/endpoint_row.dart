// endpoint_row.dart — the provider endpoint row and the ONE credential
// ranking every surface (Chat default, model picker, Endpoints roster)
// sorts by. Split from gateway_models.dart to hold the size gate; that file
// re-exports this one, so imports stay stable.

/// A provider endpoint row (GET /api/endpoints).
class EndpointRow {
  final String name;
  final String backend;
  final String credential; // present | absent | local-none | cli-auth
  final String providerRole;
  final bool configured;

  EndpointRow({
    required this.name,
    required this.backend,
    required this.credential,
    required this.providerRole,
    required this.configured,
  });

  factory EndpointRow.fromJson(Map<String, dynamic> j) => EndpointRow(
        name: j['name'] ?? j['model'] ?? '',
        backend: j['backend'] ?? '',
        credential: j['credential'] ?? 'absent',
        providerRole: j['provider_role'] ?? '',
        configured: j['configured'] ?? false,
      );

  bool get hasCredential => credential == 'present' || credential == 'cli-auth';

  /// A row a first send can actually answer through: a signed-in
  /// subscription CLI, a present key, or a local tier.
  bool get usable =>
      credential == 'cli-auth' ||
      credential == 'present' ||
      credential == 'local-none';
}

/// The one credential ranking every surface sorts by: subscription tier
/// first (the paid-for CLI), then keyed/local, then unusable.
int endpointRank(EndpointRow e) => switch (e.credential) {
      'cli-auth' => 0,
      'present' => 1,
      'local-none' => 1,
      _ => 2,
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
