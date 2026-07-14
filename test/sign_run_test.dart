// The sign-this-run panel: ownership as a workflow. Checkboxes come from
// the run's own review (files the agent edited), coverage is computed by
// the engine, and the standing renders as the verdict it is: complete or
// honestly partial. The evidence card renders what a run can prove.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/attestation_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/run_evidence_card.dart';
import 'package:flywheel_desktop/widgets/sign_run_panel.dart';

const _run = {
  'checkpoint': 'abc123',
  'review': {
    'files_edited': ['a.py', 'b.py'],
    'files_read': ['a.py', 'b.py'],
    'reviewability': 0.9,
  },
};

void main() {
  testWidgets('RunEvidenceCard renders the ttva null honestly',
      (tester) async {
    const run = {
      'duration_s': 4.2,
      'ttva_s': null,
      'context_manifest': {
        'reads': [
          {'path': 'a.py', 'content_sha256': 'x'}
        ],
        'tools': {'read_file': 1},
      },
      'risk_review': {'demands': []},
      'workspace': {'changed': false},
      'run_receipt': {'chain_hash': 'abc123def456'},
    };
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: const Scaffold(
          body: SingleChildScrollView(child: RunEvidenceCard(run: run))),
    ));
    await tester.pump();
    expect(find.textContaining('null: nothing verified'), findsOneWidget);
    expect(find.textContaining('1 reads'), findsOneWidget);
    expect(find.textContaining('unchanged'), findsOneWidget);
  });

  test('Attestation parses standing, coverage, and store receipt', () {
    final a = Attestation.fromJson(const {
      'schema': 'flywheel.attestation/v1',
      'standing': 'partial',
      'coverage': 0.5,
      'reviewed': ['a.py'],
      'unreviewed': ['b.py'],
      'overclaimed': [],
      'sha256': 'deadbeef',
      'stored': 'eid123',
      'store_chain_hash': 'chain456',
    });
    expect(a.standing, 'partial');
    expect(a.verdict, 'unverifiable'); // partial ownership is not dressed up
    expect(a.coverage, 0.5);
    expect(a.unreviewed, ['b.py']);
    expect(a.stored, 'eid123');
  });

  test('complete standing renders verified', () {
    final a = Attestation.fromJson(const {
      'standing': 'complete',
      'coverage': 1.0,
      'sha256': 'x',
    });
    expect(a.verdict, 'verified');
  });

  testWidgets('high-risk demands gate the sign button until walked',
      (tester) async {
    const risky = {
      'checkpoint': 'xyz',
      'review': {
        'files_edited': ['g.py', 'a.py'],
      },
      'risk_review': {
        'demands': [
          {'path': 'g.py', 'tier': 'high', 'requires': 'stronger receipt'},
        ],
      },
    };
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: SignRunPanel(client: GatewayClient(), run: risky),
        ),
      ),
    ));
    await tester.pump();
    expect(find.textContaining('high risk'), findsOneWidget);
    final sign = find.widgetWithText(FilledButton, 'Sign');
    expect(tester.widget<FilledButton>(sign).onPressed, isNull,
        reason: 'unwalked high-risk edit must gate the sign button');
    // Walking the demanded file unlocks signing.
    await tester.tap(find.byType(Checkbox).first); // g.py listed first
    await tester.pump();
    expect(tester.widget<FilledButton>(sign).onPressed, isNotNull);
  });

  testWidgets('SignRunPanel lists the edited files as walk checkboxes',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: SignRunPanel(client: GatewayClient(), run: _run),
      ),
    ));
    await tester.pump();
    expect(find.text('a.py'), findsOneWidget);
    expect(find.text('b.py'), findsOneWidget);
    expect(find.byType(Checkbox), findsNWidgets(2));
    expect(find.textContaining('0/2'), findsOneWidget);
    await tester.tap(find.byType(Checkbox).first);
    await tester.pump();
    expect(find.textContaining('1/2'), findsOneWidget);
  });
}
