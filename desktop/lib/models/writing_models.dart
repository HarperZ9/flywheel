class WritingStatus {
  final List<WritingProjectSummary> projects;
  const WritingStatus({required this.projects});

  factory WritingStatus.fromJson(Map<String, dynamic> json) {
    return WritingStatus(projects: [
      for (final row in _records(json['projects']))
        WritingProjectSummary.fromJson(row),
    ]);
  }
}

class WritingProjectSummary {
  final String projectRef, journeyRef, eventHeadSha256, title;
  final List<String> sectionRefs;

  const WritingProjectSummary({
    required this.projectRef,
    required this.journeyRef,
    required this.eventHeadSha256,
    required this.sectionRefs,
    required this.title,
  });

  factory WritingProjectSummary.fromJson(Map<String, dynamic> json) {
    final projectRef = _text(json['project_ref']);
    return WritingProjectSummary(
      projectRef: projectRef,
      journeyRef: _text(json['journey_ref']),
      eventHeadSha256: _text(json['event_head_sha256']),
      sectionRefs: _strings(json['section_refs']),
      title: _text(json['title'], fallback: projectRef.isEmpty ? 'Writing project' : projectRef),
    );
  }
}

class WritingSection {
  final String sectionRef, heading, purpose;
  final String? currentRevisionRef, currentBodySha256, currentBody;
  final int orderIndex;

  const WritingSection({
    required this.sectionRef,
    required this.heading,
    required this.purpose,
    required this.orderIndex,
    this.currentRevisionRef,
    this.currentBodySha256,
    this.currentBody,
  });

  factory WritingSection.fromJson(Map<String, dynamic> json) => WritingSection(
        sectionRef: _text(json['section_ref']),
        heading: _text(json['heading'], fallback: 'Section'),
        purpose: _text(json['purpose']),
        orderIndex: _int(json['order_index']),
        currentRevisionRef: _optionalText(json['current_revision_ref']),
        currentBodySha256: _optionalText(json['current_body_sha256']),
        currentBody: _optionalText(json['current_body']),
      );
}

class WritingProjectView {
  final String projectRef, journeyRef, eventHeadSha256;
  final Map<String, dynamic> sourcePacket;
  final List<WritingSection> sections;
  final List<Map<String, dynamic>> diagnostics, cards, candidates;
  final List<Map<String, dynamic>> decisions, reviews, exports;
  final List<String> doesNotProve;

  const WritingProjectView({
    required this.projectRef,
    required this.journeyRef,
    required this.eventHeadSha256,
    required this.sourcePacket,
    required this.sections,
    required this.diagnostics,
    required this.cards,
    required this.candidates,
    required this.decisions,
    required this.reviews,
    required this.exports,
    required this.doesNotProve,
  });

  factory WritingProjectView.fromJson(Map<String, dynamic> json) {
    return WritingProjectView(
      projectRef: _text(json['project_ref']),
      journeyRef: _text(json['journey_ref']),
      eventHeadSha256: _text(json['event_head_sha256']),
      sourcePacket: _map(json['source_packet']),
      sections: [
        for (final row in _records(json['sections'])) WritingSection.fromJson(row),
      ],
      diagnostics: _records(json['diagnostics']),
      cards: _records(json['cards']),
      candidates: _records(json['candidates']),
      decisions: _records(json['decisions']),
      reviews: _records(json['reviews']),
      exports: _records(json['exports']),
      doesNotProve: _strings(json['does_not_prove']),
    );
  }

  WritingSection? get firstCurrentSection {
    for (final section in sections) {
      if ((section.currentRevisionRef ?? '').isNotEmpty) return section;
    }
    return sections.isEmpty ? null : sections.first;
  }

  String? get firstCardRef => _firstRef(cards, 'card_ref');
  String? get firstCandidateRef => _firstRef(candidates, 'candidate_ref');
}

class WritingProposal {
  final String proposalRef, artifactId, artifactKind, scopeVerdict;
  final bool approvalRequired;

  const WritingProposal({
    required this.proposalRef,
    required this.artifactId,
    required this.artifactKind,
    required this.approvalRequired,
    this.scopeVerdict = '',
  });

  factory WritingProposal.fromJson(Map<String, dynamic> json) => WritingProposal(
        proposalRef: _text(json['proposal_ref']),
        artifactId: _text(json['artifact_id']),
        artifactKind: _text(json['artifact_kind']),
        approvalRequired: json['approval_required'] == true,
        scopeVerdict: _text(json['scope_verdict']),
      );
}

class WritingProposalPreview {
  final String proposalRef;
  final Map<String, dynamic> approvalPreview;

  const WritingProposalPreview({
    required this.proposalRef,
    required this.approvalPreview,
  });

  factory WritingProposalPreview.fromJson(Map<String, dynamic> json) {
    return WritingProposalPreview(
      proposalRef: _text(json['proposal_ref']),
      approvalPreview: _map(json['approval_preview']),
    );
  }

  Map<String, dynamic> get exactDiff => _map(approvalPreview['exact_diff']);
  String get diffBefore => _text(exactDiff['before']);
  String get diffAfter => _text(exactDiff['after']);
  String get beforeSha256 => _text(exactDiff['before_sha256']);
  String get afterSha256 => _text(exactDiff['after_sha256']);
}

String _text(Object? raw, {String fallback = ''}) => raw is String ? raw : fallback;
String? _optionalText(Object? raw) => raw is String ? raw : null;
int _int(Object? raw) => raw is int ? raw : raw is num ? raw.toInt() : 0;

List<String> _strings(Object? raw) => raw is List
    ? [for (final item in raw) if (item is String) item]
    : const [];

Map<String, dynamic> _map(Object? raw) => raw is Map
    ? Map<String, dynamic>.from(raw)
    : <String, dynamic>{};

List<Map<String, dynamic>> _records(Object? raw) => raw is List
    ? [for (final item in raw) if (item is Map) Map<String, dynamic>.from(item)]
    : const [];

String? _firstRef(List<Map<String, dynamic>> rows, String key) {
  for (final row in rows) {
    final value = row[key];
    if (value is String && value.isNotEmpty) return value;
  }
  return null;
}
