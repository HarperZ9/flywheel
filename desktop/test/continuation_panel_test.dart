import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/continuation_api.dart';
import 'package:flywheel_desktop/models/continuation_models.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/continuation_panel.dart';

const _sha = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _head =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

ContinuationPreview _preview({bool blocked = false}) =>
    ContinuationPreview.fromJson({
      'schema': 'flywheel.native-continuation-preview/v1',
      'preview_ref': 'cpv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'preview_sha256': _sha,
      'source_state_sha256': _sha,
      'intake_ref':
          'continuation/cpv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.intake.json',
      'source': {
        'root': r'C:\work\repo',
        'export_path': r'C:\work\export.jsonl'
      },
      'repo': {
        'state': 'git',
        'branch': 'main',
        'head': _sha,
        'dirty_files': [
          {'path': 'lib/main.dart', 'status': ' M', 'sha256': _sha}
        ]
      },
      'import': {
        'mappings': [
          {
            'source': 'AGENTS.md',
            'mapped_to': 'instructions',
            'status': 'mapped'
          }
        ],
        'dropped': [
          {
            'source': '.claude/settings.json',
            'reason': 'hooks have no native equivalent yet'
          }
        ],
        'mcp_server_count': 1,
      },
      'export': {
        'state': 'read',
        'signals': [
          {'kind': 'user_direction', 'line': 1, 'sha256': _sha}
        ]
      },
      'context_package': {
        'schema': 'flywheel.native-continuation-context/v1',
        'selected_tasks': [
          'Fix parser behavior without exposing this raw text in chrome'
        ],
        'selected_summaries': const [],
        'selected_files': ['lib/parser.dart'],
        'commits': const [],
      },
      'runner_context': {
        'schema': 'flywheel.native-continuation-runner-context/v1',
        'root': r'C:\\work\\repo',
        'goal': 'Private runner prompt',
        'selected_files': ['lib/parser.dart'],
      },
      'provider_native_resume': {
        'state': 'unavailable',
        'reason': 'no connector proved read, list, resume, or fork support'
      },
      'health': {
        'state': blocked ? 'blocked' : 'ready',
        'blocking_omissions': blocked ? ['MISSING_ATTACHMENT'] : const []
      },
      'omissions': blocked
          ? [
              {'code': 'MISSING_ATTACHMENT', 'path_hint': 'song.mp3'}
            ]
          : const [],
      'next_action':
          'start a provider-neutral Evidence Journey with fresh grants',
    });

JourneyMutationAck _ack() => JourneyMutationAck.fromJson({
      'schema': 'flywheel.evidence-journey-mutation-ack/v2',
      'journey_ref': _journey,
      'event_head_sha256': _head,
      'event_sha256': _head,
      'projection_sha256': _sha,
      'idempotent_replay': false,
    });

class FakeContinuationApi implements ContinuationApi {
  ContinuationPreview previewResult = _preview();
  ContinuationFailure? startFailure;
  final calls = <String>[];

  @override
  Future<ContinuationPreview> preview(
      {required String root, String? exportPath}) async {
    calls.add('preview:$root:$exportPath');
    return previewResult;
  }

  @override
  Future<ContinuationStartResult> start(ContinuationPreview preview) async {
    calls.add('start:${preview.previewRef}');
    final failure = startFailure;
    if (failure != null) throw ContinuationApiException(failure);
    return ContinuationStartResult(
        journey: _ack(),
        previewRef: preview.previewRef,
        openLens: JourneyLens.rescue);
  }

  @override
  Future<ContinuationPrivateContext> privateContext(
      ContinuationPreview preview) async {
    throw UnimplementedError();
  }

  @override
  Future<ContinuationUndoResult> undo({
    required String journeyRef,
    required String expectedEventHead,
    required ContinuationPreview preview,
  }) async {
    throw UnimplementedError();
  }
}

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('panel previews local state and opens Rescue after start',
      (tester) async {
    final api = FakeContinuationApi();
    (String, JourneyLens)? opened;
    await tester.pumpWidget(_wrap(ContinuationPanel(
        api: api,
        alive: true,
        onOpenJourney: (ref, lens) => opened = (ref, lens))));
    await tester.enterText(
        find.byKey(const Key('continuation-root')), r'C:\work\repo');
    await tester.enterText(
        find.byKey(const Key('continuation-export')), r'C:\work\export.jsonl');
    await tester.tap(find.text('Preview continuation'));
    await tester.pumpAndSettle();
    expect(find.textContaining('dirty 1'), findsOneWidget);
    expect(find.text('private context 1 task · 1 file'), findsOneWidget);
    expect(find.textContaining('lib/parser.dart'), findsOneWidget);
    expect(find.text('provider-native resume unavailable'), findsOneWidget);
    await tester.tap(find.text('Start Journey'));
    await tester.pumpAndSettle();
    expect(opened, (_journey, JourneyLens.rescue));
    expect(api.calls, [
      r'preview:C:\work\repo:C:\work\export.jsonl',
      'start:cpv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    ]);
  });

  testWidgets('stale source failure keeps preview visible and fixed',
      (tester) async {
    final api = FakeContinuationApi()
      ..startFailure = const ContinuationFailure(
          'SOURCE_DRIFT', 'Source changed since preview; preview again.');
    await tester.pumpWidget(_wrap(
        ContinuationPanel(api: api, alive: true, onOpenJourney: (_, __) {})));
    await tester.enterText(
        find.byKey(const Key('continuation-root')), r'C:\work\repo');
    await tester.tap(find.text('Preview continuation'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Start Journey'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Source changed since preview'), findsOneWidget);
    expect(find.textContaining('dirty 1'), findsOneWidget);
  });

  testWidgets('blocked missing state keeps Start disabled', (tester) async {
    final api = FakeContinuationApi()..previewResult = _preview(blocked: true);
    await tester.pumpWidget(_wrap(
        ContinuationPanel(api: api, alive: true, onOpenJourney: (_, __) {})));
    await tester.enterText(
        find.byKey(const Key('continuation-root')), r'C:\work\repo');
    await tester.tap(find.text('Preview continuation'));
    await tester.pumpAndSettle();
    expect(find.text('BLOCKED'), findsOneWidget);
    expect(find.textContaining('song.mp3'), findsOneWidget);
    final button = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Start Journey'));
    expect(button.onPressed, isNull);
  });
}
