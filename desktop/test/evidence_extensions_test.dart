// The contextual extension widgets: absent capabilities render nothing,
// execution-locked ones state their lock, and no widget derives truth.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/evidence_extensions.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/evidence_extensions.dart';
import 'package:flywheel_desktop/widgets/fw.dart';

EvidenceCapability _cap(String state) => EvidenceCapability(
      id: 'incident-compiler',
      schema: 'flywheel.incident-case/v1',
      state: state,
      reason: 'data admissible; process containment not accepted',
      contractSha256: 'a' * 64,
      operations: const ['incident.propose'],
      limits: const {'max_source_refs': 32},
    );

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: ListView(children: [child])),
    );

void main() {
  testWidgets('an absent capability renders nothing at all', (tester) async {
    await tester.pumpWidget(_wrap(const IncidentExtension(capability: null)));
    await tester.pump();
    expect(find.textContaining('incident compiler'), findsNothing);
    expect(find.byType(HairlineCard), findsNothing);
  });

  testWidgets('an unknown-state capability renders nothing', (tester) async {
    await tester.pumpWidget(
        _wrap(IncidentExtension(capability: _cap('something_new'))));
    await tester.pump();
    expect(find.byType(HairlineCard), findsNothing);
  });

  testWidgets('an execution-locked capability states its lock in text',
      (tester) async {
    await tester.pumpWidget(_wrap(DomainPackExtension(
        capability: _cap('execution_locked'))));
    await tester.pump();
    expect(find.textContaining('Execution locked'), findsOneWidget);
  });

  testWidgets('a proposal renders as proposed with its does-not-prove',
      (tester) async {
    await tester.pumpWidget(_wrap(IncidentExtension(
      capability: _cap('available'),
      proposal: IncidentProposal(
          proposalId: 'prp_${'a' * 32}',
          state: 'proposed',
          journeyRef: 'jrn_${'a' * 32}',
          doesNotProve: 'a proposed graph is not a diagnosis'),
    )));
    await tester.pump();
    expect(find.textContaining('proposed'), findsWidgets);
    expect(find.textContaining('not a diagnosis'), findsOneWidget);
    expect(find.text('Accept'), findsNothing,
        reason: 'a proposal cannot be accepted from the client');
  });

  testWidgets('frontier axes render per axis with raw values preserved',
      (tester) async {
    await tester.pumpWidget(_wrap(FrontierClaimExtension(
      capability: EvidenceCapability(
          id: 'frontier-claims',
          schema: 'flywheel.frontier-claim/v1',
          state: 'available',
          reason: 'accepted',
          contractSha256: 'a' * 64,
          operations: const ['frontier.project'],
          limits: const {}),
      axes: FrontierAxes(claimId: 'clm_${'a' * 8}', axes: [
        FrontierAxis(
            axis: 'value',
            fields: {'novelty_state': 'NOT_FOUND_IN_CORPUS'},
            rawUnrecognized: []),
      ]),
    )));
    await tester.pump();
    expect(find.textContaining('NOT_FOUND_IN_CORPUS'), findsOneWidget);
    expect(find.textContaining('score'), findsNothing);
  });

  test('defensive decoding degrades unknown rows to hidden', () {
    final capabilities = EvidenceCapabilities.fromJson({
      'capabilities': [
        {'id': 'good', 'schema': 's', 'state': 'available',
         'reason': 'r', 'contract_sha256': 'a' * 64,
         'operations': ['op'], 'limits': {}},
        {'id': 42},
        'garbage',
      ],
    });
    expect(capabilities.capabilities, hasLength(1));
    expect(capabilities.byId('good'), isNotNull);
    expect(capabilities.byId('42'), isNull);
  });
}
