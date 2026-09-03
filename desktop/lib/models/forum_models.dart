// forum_models.dart - the forum lane's four reads, parsed defensively.
//
// Every field degrades rather than crashes: the lane can be offline, an older
// lane can omit a counter, and a newer one can add fields this build has never
// seen. A view that cannot render "the lane is down" is not shippable, so the
// offline case is a first-class value here rather than an exception.

/// The lane is either reachable or it is not, and the reason is the lane's own
/// words. Never synthesized.
class ForumOffline {
  final String reason;
  const ForumOffline(this.reason);

  /// The gateway returns `{"error": ...}` when the MCP lane is unreachable.
  static ForumOffline? from(Map<String, dynamic> json) {
    final err = json['error'];
    return err is String && err.isNotEmpty ? ForumOffline(err) : null;
  }
}

int _int(Object? v) => v is int ? v : (v is num ? v.toInt() : 0);

class ForumStatus {
  final ForumOffline? offline;
  final String version;
  final String role;

  /// The lane's own verdict string. Rendered as a verdict, never recomputed.
  final String status;
  final String currentStatus;

  const ForumStatus({
    this.offline,
    this.version = '',
    this.role = '',
    this.status = '',
    this.currentStatus = '',
  });

  factory ForumStatus.fromJson(Map<String, dynamic> json) {
    final off = ForumOffline.from(json);
    if (off != null) return ForumStatus(offline: off);
    final native = json['native'];
    final n = native is Map<String, dynamic> ? native : const {};
    return ForumStatus(
      version: '${json['tool_version'] ?? ''}',
      role: '${n['role'] ?? ''}',
      status: '${json['status'] ?? ''}',
      currentStatus: '${n['current_status'] ?? ''}',
    );
  }
}

class ForumLedger {
  final ForumOffline? offline;
  final int entries;
  final int requests;
  final int tasks;
  final int answers;
  final int escalations;
  final int budgetStops;
  final int payloadBytes;
  final String checkpoint;

  /// The lane's own chain verdict. An intact chain is not answer acceptance,
  /// and the view says so rather than letting a green tick imply it.
  final bool verified;

  const ForumLedger({
    this.offline,
    this.entries = 0,
    this.requests = 0,
    this.tasks = 0,
    this.answers = 0,
    this.escalations = 0,
    this.budgetStops = 0,
    this.payloadBytes = 0,
    this.checkpoint = '',
    this.verified = false,
  });

  factory ForumLedger.fromJson(Map<String, dynamic> json) {
    final off = ForumOffline.from(json);
    if (off != null) return ForumLedger(offline: off);
    return ForumLedger(
      entries: _int(json['entries']),
      requests: _int(json['requests']),
      tasks: _int(json['tasks']),
      answers: _int(json['answers']),
      escalations: _int(json['escalations']),
      budgetStops: _int(json['budget_stops']),
      payloadBytes: _int(json['payload_bytes']),
      checkpoint: '${json['checkpoint'] ?? ''}',
      verified: json['verified'] == true,
    );
  }

  /// An all-zero ledger is empty, which is a real state and not a failure.
  bool get isEmpty => entries == 0;
}

class ForumGate {
  final int runSeq;
  final int wave;
  final String label;

  const ForumGate(
      {required this.runSeq, required this.wave, required this.label});

  factory ForumGate.fromJson(Map<String, dynamic> json) => ForumGate(
        runSeq: _int(json['run_seq']),
        wave: _int(json['wave']),
        label: '${json['label'] ?? json['reason'] ?? ''}',
      );
}

class ForumGates {
  final ForumOffline? offline;
  final List<ForumGate> pending;
  const ForumGates({this.offline, this.pending = const []});

  factory ForumGates.fromJson(Map<String, dynamic> json) {
    final off = ForumOffline.from(json);
    if (off != null) return ForumGates(offline: off);
    final raw = json['pending'];
    return ForumGates(
      pending: raw is List
          ? [
              for (final g in raw)
                if (g is Map<String, dynamic>) ForumGate.fromJson(g)
            ]
          : const [],
    );
  }
}

class ForumRunRoom {
  final ForumOffline? offline;

  /// The lane's operator brief. Rendered as written; the client composes no
  /// summary of its own, because a second summary is a second claim.
  final String state;
  final String title;
  final String summary;
  final String risk;
  final String nextStep;
  final List<String> bullets;
  final int pendingGates;
  final int failedResults;
  final int verificationsRan;
  final bool verified;

  const ForumRunRoom({
    this.offline,
    this.state = '',
    this.title = '',
    this.summary = '',
    this.risk = '',
    this.nextStep = '',
    this.bullets = const [],
    this.pendingGates = 0,
    this.failedResults = 0,
    this.verificationsRan = 0,
    this.verified = false,
  });

  factory ForumRunRoom.fromJson(Map<String, dynamic> json) {
    final off = ForumOffline.from(json);
    if (off != null) return ForumRunRoom(offline: off);
    final b = json['brief'];
    final brief = b is Map<String, dynamic> ? b : const {};
    final s = json['signals'];
    final signals = s is Map<String, dynamic> ? s : const {};
    final rawBullets = brief['bullets'];
    return ForumRunRoom(
      state: '${brief['state'] ?? ''}',
      title: '${brief['title'] ?? ''}',
      summary: '${brief['summary'] ?? ''}',
      risk: '${brief['risk'] ?? ''}',
      nextStep: '${brief['next_step'] ?? ''}',
      bullets: rawBullets is List
          ? [for (final x in rawBullets) '$x']
          : const [],
      pendingGates: _int(signals['pending_gates']),
      failedResults: _int(signals['failed_results']),
      verificationsRan: _int(signals['verifications_ran']),
      verified: json['verified'] == true,
    );
  }

  bool get idle => state == 'idle';
}
