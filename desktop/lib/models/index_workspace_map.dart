import 'evidence_state.dart';

final _rootHashPrefixPattern = RegExp(r'^[0-9a-f]{0,64}$');
final _indexJobStatus = RegExp(
  r'^(queued|running|cancellation_requested|cancelled|failed|complete|unknown)$',
);
final _indexJobPhase = RegExp(r'^[a-z0-9_.:-]{0,64}$');

String _readLocalDetail(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw == null) return '';
  if (raw is String && isSafeLocalPath(raw)) return raw;
  addParseIssue(issues, field, raw);
  return '';
}

class IndexWorkspaceMapJob extends DefensiveModel {
  final String root;
  final String rootSha256Prefix;
  final String jobId;
  final String status;
  final String phase;
  final int completedRepos;
  final int? totalRepos;
  final bool resultAvailable;
  final String? resultSha256;
  final String? errorType;
  final String? message;
  final String? content;

  IndexWorkspaceMapJob({
    required this.root,
    required this.rootSha256Prefix,
    required this.jobId,
    required this.status,
    required this.phase,
    required this.completedRepos,
    required this.totalRepos,
    required this.resultAvailable,
    required this.resultSha256,
    required this.errorType,
    required this.message,
    required this.content,
    required List<ParseIssue> parseIssues,
  }) : super(parseIssues);

  factory IndexWorkspaceMapJob.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, 'flywheel.index-workspace-map-job/v1', issues);
    final total = json['total_repos'];
    if (total != null && (total is! int || total < 0)) {
      addParseIssue(issues, 'total_repos', total);
    }
    final completed = readValue<int>(json, 'completed_repos', issues, 0);
    if (completed < 0) addParseIssue(issues, 'completed_repos', completed);
    final resultHash = readText(
      json,
      'result_sha256',
      issues,
      optional: true,
      pattern: sha256Pattern,
    );
    final error = readText(json, 'error_type', issues, optional: true);
    final detail = _readLocalDetail(json, 'message', issues);
    final body = _readLocalDetail(json, 'content', issues);
    return IndexWorkspaceMapJob(
      root: readText(json, 'root', issues, pattern: RegExp(r'.+')),
      rootSha256Prefix: readText(
        json,
        'root_sha256_prefix',
        issues,
        optional: true,
        pattern: _rootHashPrefixPattern,
      ),
      jobId: readText(json, 'job_id', issues, optional: true),
      status: readText(json, 'status', issues, pattern: _indexJobStatus),
      phase: readText(
        json,
        'phase',
        issues,
        optional: true,
        pattern: _indexJobPhase,
      ),
      completedRepos: completed < 0 ? 0 : completed,
      totalRepos: total is int && total >= 0 ? total : null,
      resultAvailable: readValue<bool>(json, 'result_available', issues, false),
      resultSha256: resultHash.isEmpty ? null : resultHash,
      errorType: error.isEmpty ? null : error,
      message: detail.isEmpty ? null : detail,
      content: body.isEmpty ? null : body,
      parseIssues: issues,
    );
  }

  bool get active =>
      status == 'queued' ||
      status == 'running' ||
      status == 'cancellation_requested';
  bool get cancellable =>
      (status == 'queued' || status == 'running') && jobId.isNotEmpty;
  bool get resumable =>
      (status == 'failed' || status == 'cancelled') && jobId.isNotEmpty;
  bool get complete => status == 'complete';

  String get progressLabel =>
      totalRepos == null ? '$completedRepos' : '$completedRepos / $totalRepos';

  String get displayPhase => phase.isEmpty ? status : phase;
}
