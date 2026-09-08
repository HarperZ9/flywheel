import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/index_workspace_map_api.dart';
import 'package:flywheel_desktop/controllers/index_workspace_map_controller.dart';
import 'package:flywheel_desktop/models/index_workspace_map.dart';

const _rootA = r'C:\work\a';
const _rootB = r'C:\work\b';
const _hashA = 'aaaaaaaaaaaaaaaa';
const _hashB = 'bbbbbbbbbbbbbbbb';

void main() {
  test('late root A responses cannot replace selected root B', () async {
    final api = _RaceApi();
    final controller = IndexWorkspaceMapController(api: api, poll: false);
    addTearDown(controller.dispose);

    final openA = controller.open(_rootA);
    await Future<void>.delayed(Duration.zero);
    final openB = controller.open(_rootB);
    await Future<void>.delayed(Duration.zero);

    api.completeStatus(_rootB, _job(_rootB, 'job-b', _hashB));
    api.completeSummary(_rootB, _summary(_rootB, _hashB));
    await openB;

    api.completeStatus(_rootA, _job(_rootA, 'job-a', _hashA));
    api.completeSummary(_rootA, _summary(_rootA, _hashA));
    await openA;

    expect(controller.root, _rootB);
    expect(controller.job?.jobId, 'job-b');
    expect(controller.summary?['root_sha256_prefix'], _hashB);
  });

  test(
    'switching roots does not cancel A and cancel applies to active B',
    () async {
      final api = _RaceApi();
      final controller = IndexWorkspaceMapController(api: api, poll: false);
      addTearDown(controller.dispose);

      final openA = controller.open(_rootA);
      await Future<void>.delayed(Duration.zero);
      api.completeStatus(_rootA, _job(_rootA, 'job-a', _hashA));
      api.completeSummary(_rootA, _summary(_rootA, _hashA));
      await openA;

      final openB = controller.open(_rootB);
      await Future<void>.delayed(Duration.zero);
      api.completeStatus(_rootB, _job(_rootB, 'job-b', _hashB));
      api.completeSummary(_rootB, _summary(_rootB, _hashB));
      await openB;

      expect(api.cancelled, isEmpty);
      await controller.cancel();
      expect(api.cancelled, [(_rootB, 'job-b')]);
    },
  );

  test(
    'no job status starts a new workspace map for the selected root',
    () async {
      final api = _RaceApi()..statusNoJob = true;
      final controller = IndexWorkspaceMapController(api: api, poll: false);
      addTearDown(controller.dispose);

      final opened = controller.open(_rootA);
      await Future<void>.delayed(Duration.zero);
      api.completeSummary(_rootA, _summary(_rootA, _hashA));
      api.completeStart(_rootA, _job(_rootA, 'job-started', _hashA));
      await opened;

      expect(api.started, [_rootA]);
      expect(controller.job?.jobId, 'job-started');
    },
  );

  test(
    'reopening a cancelled job allows resume on the recovered job',
    () async {
      final api = _RaceApi()
        ..statusOverride = _job(_rootA, 'job-cancelled', _hashA,
            status: 'cancelled');
      final controller = IndexWorkspaceMapController(api: api, poll: false);
      addTearDown(controller.dispose);

      final opened = controller.open(_rootA);
      await Future<void>.delayed(Duration.zero);
      api.completeSummary(_rootA, _summary(_rootA, _hashA));
      await opened;

      expect(controller.job?.status, 'cancelled');
      expect(controller.job?.resumable, isTrue);
      await controller.resume();
      expect(api.resumed, [(_rootA, 'job-cancelled')]);
    },
  );

  test(
    'updating a completed snapshot starts a new job and ignores late old result',
    () async {
      final api = _RaceApi()
        ..statusOverride = _job(_rootA, 'job-old', _hashA, status: 'complete');
      final controller = IndexWorkspaceMapController(api: api, poll: false);
      addTearDown(controller.dispose);

      final opened = controller.open(_rootA);
      await Future<void>.delayed(Duration.zero);
      api.completeSummary(_rootA, _summary(_rootA, _hashA));
      await opened;

      expect(controller.job?.jobId, 'job-old');
      expect(controller.job?.resultAvailable, isTrue);

      final oldResult = controller.retrieveResult();
      await Future<void>.delayed(Duration.zero);
      api.summaries.remove(_rootA);
      final updating = controller.updateWorkspaceMap();
      await Future<void>.delayed(Duration.zero);
      expect(api.started, [_rootA]);

      api.completeSummary(_rootA, _summary(_rootA, _hashB));
      api.completeStart(
        _rootA,
        _job(_rootA, 'job-new', _hashB, status: 'complete'),
      );
      await updating;

      expect(controller.summary?['root_sha256_prefix'], _hashB);
      expect(controller.job?.jobId, 'job-new');

      api.completeResult(
        _rootA,
        'job-old',
        _job(_rootA, 'job-old', _hashA, status: 'complete', content: 'old'),
      );
      await oldResult;
      expect(controller.job?.jobId, 'job-new');
      expect(controller.job?.content, isNull);

      final newResult = controller.retrieveResult();
      await Future<void>.delayed(Duration.zero);
      expect(api.resulted, [(_rootA, 'job-old'), (_rootA, 'job-new')]);
      api.completeResult(
        _rootA,
        'job-new',
        _job(_rootA, 'job-new', _hashB, status: 'complete', content: 'new'),
      );
      await newResult;
      expect(controller.job?.jobId, 'job-new');
      expect(controller.job?.content, 'new');
    },
  );
}

Map<String, Object?> _summary(String root, String hash) => {
  'schema': 'flywheel.index-summary/v1',
  'root': root,
  'repo_count': 1,
  'dirty_count': 0,
  'class_total': 1,
  'root_sha256_prefix': hash,
  'errors': <String, Object?>{},
};

IndexWorkspaceMapJob _job(
  String root,
  String jobId,
  String hash, {
  String status = 'running',
  String? content,
}) => IndexWorkspaceMapJob.fromJson({
  'schema': 'flywheel.index-workspace-map-job/v1',
  'root': root,
  'root_sha256_prefix': hash,
  'job_id': jobId,
  'status': status,
  'phase': status == 'running' ? 'building' : status,
  'completed_repos': status == 'complete' ? 2 : 1,
  'total_repos': 2,
  'result_available': status == 'complete',
  'result_sha256': status == 'complete' ? 'c' * 64 : null,
  'error_type': null,
  'message': null,
  'content': content,
});

final class _RaceApi implements IndexWorkspaceMapApi {
  final summaries = <String, Completer<Map<String, dynamic>>>{};
  final statuses = <String, Completer<IndexWorkspaceMapJob>>{};
  final starts = <String, Completer<IndexWorkspaceMapJob>>{};
  final results = <(String, String), Completer<IndexWorkspaceMapJob>>{};
  final cancelled = <(String, String)>[];
  final resulted = <(String, String)>[];
  final resumed = <(String, String)>[];
  final started = <String>[];
  bool statusNoJob = false;
  IndexWorkspaceMapJob? statusOverride;

  void completeSummary(String root, Map<String, Object?> value) {
    summaries[root]!.complete(Map<String, dynamic>.from(value));
  }

  void completeStatus(String root, IndexWorkspaceMapJob value) {
    statuses[root]!.complete(value);
  }

  void completeStart(String root, IndexWorkspaceMapJob value) {
    starts[root]!.complete(value);
  }

  void completeResult(String root, String jobId, IndexWorkspaceMapJob value) {
    results[(root, jobId)]!.complete(value);
  }

  @override
  Future<Map<String, dynamic>> summary(String root) {
    return (summaries[root] ??= Completer<Map<String, dynamic>>()).future;
  }

  @override
  Future<IndexWorkspaceMapJob> status(String root, {String? jobId}) {
    if (statusOverride != null) {
      return Future.value(statusOverride);
    }
    if (statusNoJob) {
      return Future.value(_noJob(root));
    }
    return (statuses[root] ??= Completer<IndexWorkspaceMapJob>()).future;
  }

  @override
  Future<IndexWorkspaceMapJob> start(
    String root, {
    int maxDocs = 500,
    bool noCache = false,
  }) {
    started.add(root);
    return (starts[root] ??= Completer<IndexWorkspaceMapJob>()).future;
  }

  @override
  Future<IndexWorkspaceMapJob> cancel(String root, {String? jobId}) async {
    cancelled.add((root, jobId ?? ''));
    return _job(
      root,
      jobId ?? '',
      root == _rootA ? _hashA : _hashB,
      status: 'cancellation_requested',
    );
  }

  @override
  Future<IndexWorkspaceMapJob> result(String root, {String? jobId}) {
    final key = (root, jobId ?? '');
    resulted.add(key);
    return (results[key] ??= Completer<IndexWorkspaceMapJob>()).future;
  }

  @override
  Future<IndexWorkspaceMapJob> resume(String root, {String? jobId}) async {
    resumed.add((root, jobId ?? ''));
    return _job(root, jobId ?? '', root == _rootA ? _hashA : _hashB);
  }
}

IndexWorkspaceMapJob _noJob(String root) => IndexWorkspaceMapJob.fromJson({
  'schema': 'flywheel.index-workspace-map-job/v1',
  'root': root,
  'root_sha256_prefix': '',
  'job_id': '',
  'status': 'failed',
  'phase': 'failed',
  'completed_repos': 0,
  'total_repos': null,
  'result_available': false,
  'result_sha256': null,
  'error_type': 'NO_JOB_FOR_ROOT',
  'message': null,
});
