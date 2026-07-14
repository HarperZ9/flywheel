// science_models.dart — typed reading of a science run
// (flywheel.science-run/v1). Sources carry gather provenance, the spec is
// the same PRP shape the Plan view reads, and UNVERIFIABLE claim verdicts
// stay unverifiable — an unmeasured claim is never upgraded client-side.

import 'plan_models.dart';

class ScienceSource {
  final String id;
  final String title;
  final String url;
  const ScienceSource(
      {required this.id, required this.title, required this.url});

  factory ScienceSource.fromJson(Map<String, dynamic> j) => ScienceSource(
      id: j['id'] ?? '', title: j['title'] ?? '', url: j['url'] ?? '');
}

class ClaimVerdict {
  final String claimId;
  final String status; // MATCH | DRIFT | UNVERIFIABLE
  final String grounds;
  const ClaimVerdict(
      {required this.claimId, required this.status, required this.grounds});

  String get verdict => switch (status) {
        'MATCH' => 'verified',
        'UNVERIFIABLE' => 'unverifiable',
        _ => 'drift',
      };

  factory ClaimVerdict.fromJson(Map<String, dynamic> j) => ClaimVerdict(
        claimId: j['claim_id'] ?? '',
        status: j['status'] ?? '',
        grounds: j['grounds'] ?? '',
      );
}

class ScienceRun {
  final String question;
  final List<ScienceSource> sources;
  final ForgedPlan? plan;
  final List<ClaimVerdict> verdicts;
  final String crucible;
  final Map<String, String> errors;
  final String chainHash;

  const ScienceRun(
      {required this.question,
      required this.sources,
      this.plan,
      required this.verdicts,
      required this.crucible,
      required this.errors,
      required this.chainHash});

  factory ScienceRun.fromJson(Map<String, dynamic> j) => ScienceRun(
        question: j['question'] ?? '',
        sources: ((j['sources'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .map(ScienceSource.fromJson)
            .toList(),
        plan: j['prp'] is Map<String, dynamic>
            ? ForgedPlan.fromJson(j['prp'] as Map<String, dynamic>)
            : null,
        verdicts: ((j['verdicts'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .map(ClaimVerdict.fromJson)
            .toList(),
        crucible: j['crucible'] ?? '',
        errors: (j['errors'] is Map<String, dynamic>)
            ? (j['errors'] as Map<String, dynamic>)
                .map((k, v) => MapEntry(k, '$v'))
            : const {},
        chainHash: j['chain_hash'] ?? '',
      );
}
