import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/main.dart';
import 'package:flywheel_desktop/ide/unsaved_work_guard.dart';
import 'package:flywheel_desktop/shell/view_factory.dart';
import 'package:flywheel_desktop/views/lanes_view.dart';
import 'package:flywheel_desktop/views/receipts_view.dart';
import 'package:flywheel_desktop/widgets/fw.dart';
import 'package:flywheel_desktop/widgets/side_rail.dart';

import 'journey_controller_test.dart' show headA;
import 'journey_shell_test.dart';

const _types = <String, String>{
  'Journey': 'JourneyView',
  'Chat': 'AgentView',
  'Compare': 'CompareView',
  'Models': 'EndpointsView',
  'Code': 'CodeView',
  'Eval': 'EvalView',
  'Audit': 'AuditView',
  'Companion': 'CompanionView',
  'Plan': 'PlanView',
  'Workflows': 'WorkflowsView',
  'Studio': 'StudioView',
  'Lint': 'LintView',
  'Memory': 'MemoryView',
  'Graph': 'GraphView',
  'Projects': 'ProjectsView',
  'Feeds': 'FeedsView',
  'Discourse': 'DiscourseView',
  'Academy': 'AcademyView',
  'Lessons': 'LessonsView',
  'Governance': 'GovernanceView',
  'Receipts': 'ReceiptsView',
  'Usage': 'UsageView',
  'Instruments': 'InstrumentsView',
  'Science': 'ScienceView',
  'World': 'WorldView',
  'Lanes': 'LanesView',
  'Train': 'TrainView',
  'Uplift': 'UpliftView',
  'Family': 'FamilyView',
  'Plugins': 'PluginsView',
};

void main() {
  testWidgets('factory preserves all thirty exact destination mappings',
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
    expect(flywheelDestinations.map((item) => item.label), _types.keys);
    for (final entry in _types.entries) {
      expect(buildDestinationView(entry.key, inputs).runtimeType.toString(),
          entry.value,
          reason: entry.key);
    }
    expect(buildDestinationView('Unknown', inputs), isA<FwEmpty>());
    expect((buildDestinationView('Receipts', inputs) as ReceiptsView).focusLeaf,
        headA);
    final lanes = buildDestinationView('Lanes', inputs) as LanesView;
    expect(lanes.onProbe, isNotNull);
    expect(lanes.onInstall, isNotNull);
    await unmount(tester);
  });

  testWidgets('thirty labels remain reachable at ordinary scaled viewport',
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
    final rail = tester.widget<SideRail>(find.byType(SideRail));
    expect(rail.destinations, hasLength(30));
    for (final label in _types.keys) {
      await tester.scrollUntilVisible(find.text(label), 40,
          scrollable: find.byType(Scrollable).first);
      expect(find.text(label), findsOneWidget, reason: label);
    }
    await tester.tap(find.text('Receipts'));
    await tester.pump();
    expect(find.textContaining('receipts ledger'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await unmount(tester);
  });
}
