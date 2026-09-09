import 'bulletin_media_review.dart';
import 'evidence_state.dart';

const bulletinRunsRequestSchema = 'flywheel.bulletin-media-runs-request/v1';
const bulletinRunsResponseSchema = 'flywheel.bulletin-media-runs-response/v1';

final _runId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$');

final class BulletinMediaRun extends DefensiveModel {
  final String runId, kind, title, status, createdUtc, updatedUtc;
  final int artifactCount;
  BulletinMediaRun._(this.runId, this.kind, this.title, this.status,
      this.createdUtc, this.updatedUtc, this.artifactCount, super.parseIssues);

  factory BulletinMediaRun.fromJson(Map<String, Object?> json, String f) {
    final issues = <ParseIssue>[];
    bulletinExact(
        json,
        const {
          'run_id',
          'kind',
          'title',
          'status',
          'created_utc',
          'updated_utc',
          'artifact_count'
        },
        issues,
        f);
    return BulletinMediaRun._(
      readText(json, 'run_id', issues, pattern: _runId),
      readText(json, 'kind', issues),
      readText(json, 'title', issues),
      readText(json, 'status', issues),
      readText(json, 'created_utc', issues),
      readText(json, 'updated_utc', issues),
      bulletinReadNonNegativeInt(json, 'artifact_count', issues),
      issues,
    );
  }
}

final class BulletinMediaRunsResponse extends DefensiveModel {
  final List<BulletinMediaRun> runs;
  final String? nextCursor;
  BulletinMediaRunsResponse._(this.runs, this.nextCursor, super.parseIssues);

  factory BulletinMediaRunsResponse.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    bulletinExact(
        json, const {'schema', 'runs', 'next_cursor'}, issues, 'runs');
    expectSchema(json, bulletinRunsResponseSchema, issues);
    final rows = json['runs'];
    final runs = <BulletinMediaRun>[];
    if (rows is List) {
      for (var i = 0; i < rows.length; i++) {
        final row = rows[i];
        if (row is Map<String, Object?>) {
          final parsed = BulletinMediaRun.fromJson(row, 'runs[$i]');
          issues.addAll(parsed.parseIssues);
          runs.add(parsed);
        } else {
          addParseIssue(issues, 'runs[$i]', row);
        }
      }
    } else {
      addParseIssue(issues, 'runs', rows);
    }
    final cursor = json['next_cursor'];
    if (cursor != null && cursor is! String) {
      addParseIssue(issues, 'next_cursor', cursor);
    }
    return BulletinMediaRunsResponse._(
        List.unmodifiable(runs), cursor is String ? cursor : null, issues);
  }
}
