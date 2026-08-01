// discourse.dart — the chorus discourse digest as the app reads it.
//
// The engine's /api/discourse returns chorus's own digest verbatim under
// `result`, with a re-checkable receipt. Sentiment here is a WEIGHT, never a
// verdict, so it renders in neutral ink; the one verdict in the view is the
// receipt's verify status. Every field parses defensively: a missing field
// degrades to a null-ish default, never a crash.

double _d(Object? v) => v is num ? v.toDouble() : 0.0;
int _i(Object? v) => v is num ? v.toInt() : 0;
String _s(Object? v) => v is String ? v : '';

/// A discoverable gather corpus: one gathered run that can be synthesized.
class CorpusRef {
  final String path;
  final String name;
  final int comments;
  final String subject;
  final String respondsTo;

  const CorpusRef({
    required this.path,
    required this.name,
    required this.comments,
    required this.subject,
    required this.respondsTo,
  });

  factory CorpusRef.fromJson(Map<String, dynamic> j) => CorpusRef(
        path: _s(j['path']),
        name: _s(j['name']),
        comments: _i(j['comments']),
        subject: _s(j['subject']),
        respondsTo: _s(j['responds_to']),
      );

  static List<CorpusRef> listFrom(Map<String, dynamic> env) =>
      ((env['corpora'] as List?) ?? const [])
          .whereType<Map>()
          .map((m) => CorpusRef.fromJson(m.cast<String, dynamic>()))
          .toList();
}

/// One digest the daemon has stored: a scheduled synthesis, summarized.
class DigestRef {
  final double at;
  final String respondsTo;
  final int nItems;
  final int themes;
  final bool verified;
  final String digestSha;

  const DigestRef({
    required this.at,
    required this.respondsTo,
    required this.nItems,
    required this.themes,
    required this.verified,
    required this.digestSha,
  });

  factory DigestRef.fromJson(Map<String, dynamic> j) => DigestRef(
        at: _d(j['at']),
        respondsTo: _s(j['responds_to']),
        nItems: _i(j['n_items']),
        themes: _i(j['themes']),
        verified: j['verified'] == true,
        digestSha: _s(j['digest_sha256']),
      );

  static List<DigestRef> listFrom(Map<String, dynamic> env) =>
      ((env['digests'] as List?) ?? const [])
          .whereType<Map>()
          .map((m) => DigestRef.fromJson(m.cast<String, dynamic>()))
          .toList();
}

class DiscourseTheme {
  final String label;
  final int size;
  final double weightedScore;
  final double posShare;
  final double negShare;
  final double neuShare;
  final double meanCompound;

  /// How contested the theme is: 0 is consensus, approaching 1 as voices split
  /// hard between strong positive and strong negative. A weight, never a verdict.
  final double controversy;
  final String? dissent;

  const DiscourseTheme({
    required this.label,
    required this.size,
    required this.weightedScore,
    required this.posShare,
    required this.negShare,
    required this.neuShare,
    required this.meanCompound,
    required this.controversy,
    required this.dissent,
  });

  factory DiscourseTheme.fromJson(Map<String, dynamic> j) {
    final s = (j['sentiment'] as Map?)?.cast<String, dynamic>() ?? const {};
    final d = j['dissent'];
    return DiscourseTheme(
      label: _s(j['label']),
      size: _i(j['size']),
      weightedScore: _d(j['weighted_score']),
      posShare: _d(s['pos']),
      negShare: _d(s['neg']),
      neuShare: _d(s['neu']),
      meanCompound: _d(s['mean_compound']),
      controversy: _d(j['controversy']),
      dissent: d is String && d.isNotEmpty ? d : null,
    );
  }
}

/// A topic the corpus is genuinely split on, measured across every comment that
/// mentions it (immune to the lexical clustering that would file agreement and
/// disagreement about one topic under different themes). Shares are a weight,
/// never a verdict.
class ContestedAspect {
  final String term;
  final int mentions;
  final double posShare;
  final double negShare;
  final double score;

  const ContestedAspect({
    required this.term,
    required this.mentions,
    required this.posShare,
    required this.negShare,
    required this.score,
  });

  factory ContestedAspect.fromJson(Map<String, dynamic> j) => ContestedAspect(
        term: _s(j['term']),
        mentions: _i(j['mentions']),
        posShare: _d(j['pos']),
        negShare: _d(j['neg']),
        score: _d(j['contested']),
      );

  static List<ContestedAspect> listFrom(Object? raw) => ((raw as List?) ?? const [])
      .whereType<Map>()
      .map((m) => ContestedAspect.fromJson(m.cast<String, dynamic>()))
      .toList();
}

class DiscourseDigest {
  final bool verified;
  final String respondsTo;
  final int nItems;
  final int engagementPresent;
  final int engagementTotal;
  final String coarseness;
  final String digestSha;
  final List<DiscourseTheme> themes;
  final List<ContestedAspect> contested;

  const DiscourseDigest({
    required this.verified,
    required this.respondsTo,
    required this.nItems,
    required this.engagementPresent,
    required this.engagementTotal,
    required this.coarseness,
    required this.digestSha,
    required this.themes,
    required this.contested,
  });

  /// True when every item carried an engagement signal (likes/upvotes). When
  /// false, the ranking is sentiment-weighted only, and the view says so.
  bool get engagementComplete =>
      engagementTotal > 0 && engagementPresent == engagementTotal;

  factory DiscourseDigest.fromEnvelope(Map<String, dynamic> env) {
    final r = (env['result'] as Map?)?.cast<String, dynamic>() ?? const {};
    final method = (r['method'] as Map?)?.cast<String, dynamic>() ?? const {};
    final cov =
        (method['engagement_coverage'] as Map?)?.cast<String, dynamic>() ??
            const {};
    final receipt =
        (r['receipt'] as Map?)?.cast<String, dynamic>() ?? const {};
    final themes = ((r['themes'] as List?) ?? const [])
        .whereType<Map>()
        .map((m) => DiscourseTheme.fromJson(m.cast<String, dynamic>()))
        .toList();
    return DiscourseDigest(
      verified: env['verified'] == true,
      respondsTo: _s(r['responds_to']),
      nItems: _i(r['n_items']),
      engagementPresent: _i(cov['present']),
      engagementTotal: _i(cov['total']),
      coarseness: _s(method['coarseness']),
      digestSha: _s(receipt['digest_sha256']),
      themes: themes,
      contested: ContestedAspect.listFrom(r['contested']),
    );
  }
}
