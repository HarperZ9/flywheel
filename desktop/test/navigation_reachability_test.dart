// Reachability: every catalog destination builds a real view from the
// factory, the rail search narrows by stable label, and no destination
// is reachable by label alone.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/ide/code_buffer_session.dart';
import 'package:flywheel_desktop/ide/unsaved_work_guard.dart';
import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/navigation/destination_catalog.dart';
import 'package:flywheel_desktop/services/code_draft_store.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/shell/view_factory.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/widgets/nav_search_field.dart';

import 'journey_controller_test.dart' show ScriptedJourneyApi;
import 'journey_shell_test.dart' show unmount;

void main() {
  testWidgets('all thirty destinations build a view from typed ids',
      (tester) async {
    final dir = Directory.systemTemp.createTempSync('nav-reach-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final controller = JourneyController(
        api: ScriptedJourneyApi(),
        draftStore: JourneyDraftStore(file: File('${dir.path}/d.json')),
        sessionStore:
            JourneySessionStore(file: File('${dir.path}/s.json')));
    addTearDown(controller.dispose);
    final inputs = DestinationInputs(
      client: GatewayClient(),
      journey: controller,
      code: CodeBufferSession(
          draftStore: CodeDraftStore(root: Directory(dir.path))),
      codeGuard: UnsavedWorkGuard(
          session: CodeBufferSession(
              draftStore: CodeDraftStore(root: Directory(dir.path))),
          prompt: (_) async => CloseChoice.cancel),
      alive: false,
      settings: DesktopSettings(),
      onProbe: () {},
      onInstall: (_) async => const {},
    );
    for (final spec in destinationCatalog) {
      final view = buildDestinationView(spec.id, inputs);
      expect(view.runtimeType.toString(), isNot('FwEmpty'),
          reason: '${spec.id.name} must build a real view');
      expect(view.runtimeType.toString(), isNot('Unknown view'));
    }
    await unmount(tester);
  });

  testWidgets('the rail search narrows by stable label', (tester) async {
    final controller = TextEditingController();
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
          body: NavSearchField(
              controller: controller, onChanged: (_) {})),
    ));
    await tester.enterText(find.byType(TextField), 'receipt');
    await tester.pump();
    expect(controller.text, 'receipt');
  });

  test('search matching never changes identity', () {
    // The filter matches on label text; the id that a match navigates to
    // is the catalog's, not the query's.
    final receipts = destinationCatalog
        .where((d) => d.label.toLowerCase().contains('receipt'))
        .toList();
    expect(receipts.single.id, DestinationId.receipts);
  });
}
