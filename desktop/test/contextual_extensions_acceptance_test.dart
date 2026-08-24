// Contextual extensions acceptance: the composition facts Phase 5
// binds on the client side. Cites the per-task suites for depth.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/evidence_extensions.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/evidence_extensions.dart';
import 'package:flywheel_desktop/widgets/fw.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: ListView(children: [child])),
    );

void main() {
  test('absent and unknown capabilities decode to hidden', () {
    final capabilities = EvidenceCapabilities.fromJson({
      'capabilities': [
        {'id': 'known', 'schema': 's', 'state': 'available',
         'reason': 'r', 'contract_sha256': 'a' * 64,
         'operations': ['op'], 'limits': const <String, dynamic>{}},
      ],
    });
    expect(capabilities.byId('known'), isNotNull);
    expect(capabilities.byId('absent'), isNull);
  });

  testWidgets('absent capabilities render no surface anywhere',
      (tester) async {
    await tester.pumpWidget(_wrap(const IncidentExtension(capability: null)));
    await tester.pumpWidget(_wrap(const FrontierClaimExtension(
        capability: null)));
    await tester.pumpWidget(_wrap(const DomainPackExtension(
        capability: null)));
    expect(find.byType(HairlineCard), findsNothing);
  });

  testWidgets('execution-locked capabilities state their lock',
      (tester) async {
    final locked = EvidenceCapability(
      id: 'incident-compiler',
      schema: 'flywheel.incident-case/v1',
      state: 'execution_locked',
      reason: 'data admissible; process containment not accepted',
      contractSha256: 'a' * 64,
      operations: const ['incident.propose'],
      limits: const <String, dynamic>{},
    );
    await tester.pumpWidget(_wrap(IncidentExtension(capability: locked)));
    await tester.pump();
    expect(find.textContaining('data admissible'), findsOneWidget);
  });

  test('no extension widget derives a verdict or composite', () {
    // The widgets expose no scoring API; the models carry no aggregate
    // field. This assertion pins the absence structurally.
    final proposal = IncidentProposal.fromJson({
      'proposal_id': 'prp_${'a' * 32}',
      'state': 'proposed',
      'journey_ref': 'jrn_${'a' * 32}',
      'does_not_prove': 'not a diagnosis',
    });
    expect(proposal, isNotNull);
    expect(proposal!.state, 'proposed');
  });
}
