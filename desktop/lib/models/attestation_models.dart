// attestation_models.dart — typed reading of an attestation
// (flywheel.attestation/v1). Standing arrives computed by the engine:
// complete only at full coverage with no overclaims; partial otherwise.
// Partial ownership renders as unverifiable, never dressed up.

class Attestation {
  final String standing; // complete | partial
  final double coverage;
  final List<String> reviewed;
  final List<String> unreviewed;
  final List<String> overclaimed;
  final String sha256;
  final String stored; // store entity id, when persisted
  final String storeChainHash;

  const Attestation(
      {required this.standing,
      required this.coverage,
      required this.reviewed,
      required this.unreviewed,
      required this.overclaimed,
      required this.sha256,
      required this.stored,
      required this.storeChainHash});

  String get verdict => standing == 'complete' ? 'verified' : 'unverifiable';

  factory Attestation.fromJson(Map<String, dynamic> j) {
    List<String> strs(dynamic v) =>
        v is List ? v.map((e) => '$e').toList() : const [];
    return Attestation(
      standing: j['standing'] ?? '',
      coverage: j['coverage'] is num ? (j['coverage'] as num).toDouble() : 0,
      reviewed: strs(j['reviewed']),
      unreviewed: strs(j['unreviewed']),
      overclaimed: strs(j['overclaimed']),
      sha256: j['sha256'] ?? '',
      stored: j['stored'] ?? '',
      storeChainHash: j['store_chain_hash'] ?? '',
    );
  }
}
