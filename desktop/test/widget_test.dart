import 'dart:convert';
import 'dart:io';
import 'dart:ui' show AppExitResponse;

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/main.dart';
import 'package:flywheel_desktop/ide/code_buffer_session.dart';
import 'package:flywheel_desktop/ide/diff_view.dart';
import 'package:flywheel_desktop/ide/editor_pane.dart';
import 'package:flywheel_desktop/ide/unsaved_work_guard.dart';
import 'package:flywheel_desktop/ide/workspace.dart' as workspace;
import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/navigation/destination_catalog.dart';
import 'package:flywheel_desktop/services/code_draft_store.dart';
import 'package:flywheel_desktop/shell/view_factory.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:flywheel_desktop/views/code_view.dart';
import 'package:flywheel_desktop/views/lanes_view.dart';
import 'package:flywheel_desktop/views/receipts_view.dart';
import 'package:flywheel_desktop/widgets/flywheel_nav.dart';

import 'journey_controller_test.dart' show headA;
import 'journey_shell_test.dart';

const _types = <DestinationId, String>{
  DestinationId.journey: 'JourneyView',
  DestinationId.chat: 'AgentView',
  DestinationId.compare: 'CompareView',
  DestinationId.models: 'EndpointsView',
  DestinationId.code: 'CodeView',
  DestinationId.eval: 'EvalView',
  DestinationId.audit: 'AuditView',
  DestinationId.companion: 'CompanionView',
  DestinationId.plan: 'PlanView',
  DestinationId.workflows: 'WorkflowsView',
  DestinationId.studio: 'StudioView',
  DestinationId.lint: 'LintView',
  DestinationId.memory: 'MemoryView',
  DestinationId.graph: 'GraphView',
  DestinationId.projects: 'ProjectsView',
  DestinationId.swarms: 'SwarmsView',
  DestinationId.roadmap: 'RoadmapView',
  DestinationId.feeds: 'FeedsView',
  DestinationId.discourse: 'DiscourseView',
  DestinationId.academy: 'AcademyView',
  DestinationId.lessons: 'LessonsView',
  DestinationId.governance: 'GovernanceView',
  DestinationId.receipts: 'ReceiptsView',
  DestinationId.usage: 'UsageView',
  DestinationId.instruments: 'InstrumentsView',
  DestinationId.science: 'ScienceView',
  DestinationId.world: 'WorldView',
  DestinationId.lanes: 'LanesView',
  DestinationId.forum: 'ForumView',
  DestinationId.registry: 'RegistryView',
  DestinationId.train: 'TrainView',
  DestinationId.uplift: 'UpliftView',
  DestinationId.family: 'FamilyView',
  DestinationId.relay: 'RelayView',
  DestinationId.plugins: 'PluginsView',
  DestinationId.infra: 'InfraView',
};

void main() {
  testWidgets('factory preserves all thirty-six exact destination mappings',
      (tester) async {
    final dir = Directory.systemTemp.createTempSync('journey-factory-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final harness = ShellHarness(dir)..replyReady();
    await tester.pumpWidget(harness.app());
    await tester.pumpAndSettle();
    final inputs = DestinationInputs(
      client: harness.client,
      journey: harness.controller,
      code: harness.code,
      codeGuard: UnsavedWorkGuard(
          session: harness.code, prompt: (_) async => CloseChoice.cancel),
      alive: false,
      settings: harness.settings,
      pendingArgument: headA,
      onProbe: () {},
      onInstall: (_) async => const {},
    );
    expect(
        flywheelDestinations.map((item) => item.label).toSet(),
        _types.keys
            .map((id) =>
                id.name.substring(0, 1).toUpperCase() + id.name.substring(1))
            .toSet());
    for (final entry in _types.entries) {
      expect(buildDestinationView(entry.key, inputs).runtimeType.toString(),
          entry.value,
          reason: entry.key.name);
    }
    expect(
        (buildDestinationView(DestinationId.receipts, inputs)
                as ReceiptsView)
            .focusLeaf,
        headA);
    final lanes = buildDestinationView(DestinationId.lanes, inputs)
        as LanesView;
    expect(lanes.onProbe, isNotNull);
    expect(lanes.onInstall, isNotNull);
    await unmount(tester);
  });

  testWidgets('thirty-six labels remain reachable at ordinary scaled viewport',
      (tester) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final dir = Directory.systemTemp.createTempSync('journey-shell-routes-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final harness = ShellHarness(dir)..replyReady();
    harness.settings.uiScale = 1.4;
    await tester.pumpWidget(FlywheelApp(
        settings: harness.settings, dependencies: harness.dependencies));
    await tester.pumpAndSettle();
    for (final spec in destinationCatalog) {
      await scrollRailTo(tester, spec.label);
      expect(find.text(spec.label), findsOneWidget, reason: spec.id.name);
    }
    await tester.tap(find.text('Receipts'));
    await tester.pump();
    expect(find.textContaining('receipts ledger'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await unmount(tester);
  });
  _codeGuardWidgetTests();
  _recoveryPresentationTests();
}

/// The rail's ListView builds lazily, so a destination row may not exist
/// until scrolled into view. Drag the rail directly in small steps -- a
/// large step can jump a whole lazy build window and skip a row -- and
/// re-check after each.
Future<void> scrollRailTo(WidgetTester tester, String label) async {
  final railList = find.descendant(
    of: find.byType(AnimatedContainer),
    matching: find.byType(ListView),
  ).first;
  for (var i = 0; i < 60; i++) {
    if (find.text(label).evaluate().isNotEmpty) return;
    await tester.drag(railList, const Offset(0, -60));
    await tester.pump();
  }
}

void _prepareShellCode(ShellHarness harness) {
  final root = Directory('${harness.directory.path}/workspace')..createSync();
  final file = File('${root.path}/lib/main.dart')
    ..parent.createSync(recursive: true)
    ..writeAsStringSync('baseline');
  harness.code
    ..openWorkspace(root.path)
    ..recover()
    ..openFile(file.path);
  final open = harness.code.openFiles.single;
  harness.code.snapshot((open..controller.text = 'dirty text').path);
}

void _codeGuardWidgetTests() {
  testWidgets('rail and FlywheelNav share the same guarded code session',
      (tester) async {
    final dir = Directory.systemTemp.createTempSync('code-shell-nav-');
    addTearDown(() => dir.deleteSync(recursive: true));
    var choice = CloseChoice.cancel;
    final requests = <UnsavedWorkRequest>[];
    final harness = ShellHarness(dir, closePrompt: (request) async {
      requests.add(request);
      return choice;
    })
      ..replyReady();
    await tester.pumpWidget(harness.app());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Code'));
    await tester.pumpAndSettle();
    _prepareShellCode(harness);
    final controller = harness.code.openFiles.single.controller;
    await tester.tap(find.text('Chat'));
    await tester.pumpAndSettle();
    expect(find.byType(CodeView), findsOneWidget);
    expect(requests.single.paths, ['lib/main.dart']);
    expect(harness.code.openFiles.single.controller, same(controller));
    choice = CloseChoice.discard;
    FlywheelNav.jump(tester.element(find.byType(CodeView)), DestinationId.chat);
    await tester.pumpAndSettle();
    expect(find.byType(AgentView), findsOneWidget);
    expect(harness.code.openFiles.single.controller, same(controller));
    expect(harness.code.drafts, isEmpty);
    await unmount(tester);
  });

  testWidgets('app exit guards edits and unmount retains the latest draft',
      (tester) async {
    final dir = Directory.systemTemp.createTempSync('code-shell-exit-');
    addTearDown(() => dir.deleteSync(recursive: true));
    var choice = CloseChoice.cancel;
    final harness = ShellHarness(dir, closePrompt: (_) async => choice)
      ..replyReady();
    await tester.pumpWidget(harness.app());
    await tester.pumpAndSettle();
    _prepareShellCode(harness);
    expect(await WidgetsBinding.instance.handleRequestAppExit(),
        AppExitResponse.cancel);
    choice = CloseChoice.discard;
    expect(await WidgetsBinding.instance.handleRequestAppExit(),
        AppExitResponse.exit);
    final open = harness.code.openFiles.single;
    harness.code.snapshot((open..controller.text = 'new dirty text').path);
    final ref = workspace.workspaceReference(harness.code.workspaceRoot!);
    await unmount(tester);
    final stored = CodeDraftStore(root: Directory('${dir.path}/code'))
        .load(workspaceRef: ref);
    expect(stored.single.draft.text, 'new dirty text');
  });
}

Future<ShellHarness> _recoveryHarness(CodeRecoveryKind kind) async {
  final dir = Directory.systemTemp.createTempSync('code-recovery-view-');
  addTearDown(() => dir.deleteSync(recursive: true));
  final harness = ShellHarness(dir)..replyReady();
  final root = Directory('${dir.path}/workspace')..createSync();
  final file = File('${root.path}/main.dart')..writeAsStringSync('baseline');
  String digest(String value) => sha256.convert(utf8.encode(value)).toString();
  CodeDraftStore(root: Directory('${dir.path}/code')).save(
      workspaceRef:
          workspace.workspaceReference(root.resolveSymbolicLinksSync()),
      draft: CodeDraft(
          path: 'main.dart',
          diskSha256: digest('baseline'),
          bufferSha256: digest('draft'),
          text: 'draft',
          updatedAt: DateTime.parse('2026-08-15T12:00:00Z')));
  if (kind == CodeRecoveryKind.alreadySaved) file.writeAsStringSync('draft');
  if (kind == CodeRecoveryKind.diskChanged) file.writeAsStringSync('external');
  if (kind == CodeRecoveryKind.fileMissing) file.deleteSync();
  harness.code
    ..openWorkspace(root.path)
    ..recover();
  return harness;
}

Future<void> _pumpCodeView(WidgetTester tester, ShellHarness harness) async {
  await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
          body: CodeView(
              client: harness.client,
              alive: false,
              settings: harness.settings,
              session: harness.code,
              guard: UnsavedWorkGuard(
                  session: harness.code,
                  prompt: (_) async => CloseChoice.cancel)))));
  await tester.pumpAndSettle();
}

void _recoveryPresentationTests() {
  test('recovery blocks mutation and leave until explicit retry', () async {
    final root = Directory.systemTemp.createTempSync('code-recovery-phase-');
    final drafts = Directory.systemTemp.createTempSync('code-recovery-drafts-');
    addTearDown(() => root.deleteSync(recursive: true));
    addTearDown(() => drafts.deleteSync(recursive: true));
    final file = File('${root.path}/main.dart')..writeAsStringSync('x');
    final ref = workspace.workspaceReference(root.resolveSymbolicLinksSync());
    final foreign = File('${drafts.path}/$ref/foreign.tmp')
      ..parent.createSync(recursive: true)
      ..writeAsStringSync('x');
    final session = CodeBufferSession(draftStore: CodeDraftStore(root: drafts))
      ..openWorkspace(root.path);
    var prompts = 0;
    final guard = UnsavedWorkGuard(
        session: session,
        prompt: (_) async {
          prompts++;
          return CloseChoice.discard;
        });
    expect(await guard.requestNavigation('Chat'), isFalse);
    expect(session.recover(), isEmpty);
    expect(session.phase, CodeSessionPhase.recoveryBlocked);
    expect(() => session.openFile(file.path),
        throwsA(isA<CodeSessionException>()));
    expect(await guard.requestApplicationExit(), isFalse);
    expect(prompts, 0);
    foreign.deleteSync();
    expect(session.retryRecovery(), isTrue);
    session.openFile(file.path);
  });
  for (final entry in <CodeRecoveryKind, String>{
    CodeRecoveryKind.restored: 'Draft restored: main.dart',
    CodeRecoveryKind.alreadySaved: 'Completed save recovered: main.dart',
  }.entries) {
    testWidgets('${entry.key.name} is neutral and keeps the editor',
        (tester) async {
      final harness = await _recoveryHarness(entry.key);
      await _pumpCodeView(tester, harness);
      expect(find.text(entry.value), findsOneWidget);
      expect(find.byType(EditorPane), findsOneWidget);
      expect(find.byType(DiffViewPanel), findsNothing);
      await unmount(tester);
    });
  }
  for (final entry in <CodeRecoveryKind, String>{
    CodeRecoveryKind.diskChanged: 'main.dart: disk changed; draft retained',
    CodeRecoveryKind.fileMissing: 'main.dart: file missing; draft retained',
  }.entries) {
    testWidgets('${entry.key.name} remains an actionable comparison',
        (tester) async {
      final harness = await _recoveryHarness(entry.key);
      await _pumpCodeView(tester, harness);
      expect(find.text(entry.value), findsOneWidget);
      expect(find.byType(DiffViewPanel), findsOneWidget);
      expect(find.byType(EditorPane), findsNothing);
      await unmount(tester);
    });
  }
}
