import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/index_workspace_map.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/project_panels.dart';

void main() {
  testWidgets('workspace map panel exposes progress and cancel', (
    tester,
  ) async {
    var cancelled = 0;
    await tester.pumpWidget(
      _wrap(
        IndexPanel(
          summary: const {
            'repo_count': 1,
            'class_total': 2,
            'dirty_count': 0,
            'errors': <String, Object?>{},
          },
          job: _job('running'),
          busy: false,
          onCancel: () async => cancelled++,
          onRefresh: () async {},
          onResult: () async {},
        ),
      ),
    );

    expect(find.text('building'), findsOneWidget);
    expect(find.text('1 / 2'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('index-job-cancel')));
    expect(cancelled, 1);
  });

  testWidgets('complete workspace map offers result retrieval', (tester) async {
    var retrieved = 0;
    await tester.pumpWidget(
      _wrap(
        IndexPanel(
          summary: const {'errors': <String, Object?>{}},
          job: _job('complete'),
          busy: false,
          onCancel: () async {},
          onRefresh: () async {},
          onResult: () async => retrieved++,
        ),
      ),
    );

    expect(find.text('complete'), findsWidgets);
    expect(find.byKey(const ValueKey('index-job-result')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('index-job-result')));
    expect(retrieved, 1);
  });

  testWidgets('cancelled workspace map offers resume', (tester) async {
    var resumed = 0;
    await tester.pumpWidget(
      _wrap(
        IndexPanel(
          summary: const {'errors': <String, Object?>{}},
          job: _job('cancelled'),
          busy: false,
          onCancel: () async {},
          onRefresh: () async {},
          onResult: () async {},
          onResume: () async => resumed++,
        ),
      ),
    );

    expect(find.text('cancelled'), findsWidgets);
    await tester.tap(find.byKey(const ValueKey('index-job-resume')));
    expect(resumed, 1);
  });

  testWidgets('complete workspace map explains snapshot and offers update', (
    tester,
  ) async {
    var updated = 0;
    await tester.pumpWidget(
      _wrap(
        IndexPanel(
          summary: const {'errors': <String, Object?>{}},
          job: _job('complete'),
          busy: false,
          onCancel: () async {},
          onRefresh: () async {},
          onResult: () async {},
          onUpdate: () async => updated++,
        ),
      ),
    );

    expect(find.textContaining('snapshot'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('index-job-update')));
    expect(updated, 1);
  });
}

Widget _wrap(Widget child) => MaterialApp(
  theme: flywheelLightTheme(),
  home: Scaffold(body: SingleChildScrollView(child: child)),
);

IndexWorkspaceMapJob _job(String status) => IndexWorkspaceMapJob.fromJson({
  'schema': 'flywheel.index-workspace-map-job/v1',
  'root': r'C:\work\repo',
  'root_sha256_prefix': 'aaaaaaaaaaaaaaaa',
  'job_id': 'job-a',
  'status': status,
  'phase': status == 'running' ? 'building' : status,
  'completed_repos': status == 'complete' ? 2 : 1,
  'total_repos': 2,
  'result_available': status == 'complete',
  'result_sha256': status == 'complete' ? 'b' * 64 : null,
  'error_type': null,
  'message': null,
});
