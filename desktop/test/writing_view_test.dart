import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/writing_api.dart';
import 'package:flywheel_desktop/models/writing_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/writing_view.dart';

void main() {
  testWidgets('WritingView opens a project and drives candidate controls',
      (tester) async {
    final api = _FakeWritingApi();
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: WritingView(api: api, alive: true))));
    await tester.pumpAndSettle();
    expect(find.text('Writing'), findsOneWidget);
    expect(find.text('Release evidence'), findsOneWidget);
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(find.text('SOURCE PACKET'), findsOneWidget);
    expect(find.textContaining('Recommendation: hold.'), findsOneWidget);
    await _enterVisible(tester, find.byKey(const Key('writing-candidate-body')),
        'Recommendation: release.\n');
    await _tapVisible(tester, find.text('Prepare candidate'));
    expect(api.calls, contains('candidate:card_a'));
    expect(find.textContaining('Recommendation: release.'), findsWidgets);
    await _bringVisible(tester, _selectableTextContaining('prp_candidate'));
    expect(_selectableTextContaining('prp_candidate'), findsOneWidget);
    await _tapVisible(tester, find.text('Approve + commit proposal'));
    expect(api.calls, contains('commit:prp_candidate:gnt_prp_candidate'));
    await _tapVisible(tester, find.text('Hold latest candidate'));
    expect(api.calls, contains('decision:reject:cand_a'));
    await _enterVisible(
        tester, find.byKey(const Key('writing-export-ref')), 'final');
    await _tapVisible(tester, find.text('Prepare export'));
    expect(api.calls, contains('export:final'));
  });

  testWidgets('WritingView reports empty and gateway error states truthfully',
      (tester) async {
    final api = _FakeWritingApi.empty();
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: WritingView(api: api, alive: true))));
    await tester.pumpAndSettle();
    expect(find.textContaining('No Writing projects'), findsOneWidget);
    api.failStatus = true;
    await tester.tap(find.text('Refresh'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Gateway unavailable'), findsOneWidget);
  });
}

Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await _bringVisible(tester, finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Future<void> _enterVisible(
    WidgetTester tester, Finder finder, String value) async {
  await _bringVisible(tester, finder);
  await tester.enterText(finder, value);
}

Future<void> _bringVisible(WidgetTester tester, Finder finder) async {
  if (finder.evaluate().isEmpty) {
    await tester.scrollUntilVisible(finder, 240,
        scrollable: find.byType(Scrollable).first);
  } else {
    await tester.ensureVisible(finder);
  }
  await tester.pumpAndSettle();
}

Finder _selectableTextContaining(String value) => find.byWidgetPredicate(
    (widget) => widget is SelectableText && (widget.data ?? '').contains(value));

class _FakeWritingApi implements WritingApi {
  _FakeWritingApi() : _empty = false;
  _FakeWritingApi.empty() : _empty = true;
  final bool _empty;
  bool failStatus = false;
  final calls = <String>[];

  @override
  Future<WritingStatus> status() async {
    if (failStatus) throw Exception('Gateway unavailable');
    return WritingStatus(projects: _empty ? [] : [
      const WritingProjectSummary(
        projectRef: 'wpr_a',
        journeyRef: 'jrn_a',
        eventHeadSha256: 'h1',
        sectionRefs: ['sec_recommendation'],
        title: 'Release evidence',
      )
    ]);
  }

  @override
  Future<Map<String, dynamic>> doctor() async => const {};

  @override
  Future<WritingProjectView> project(String journeyRef) async => _project();

  @override
  Future<WritingProposal> prepareCandidate({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String cardRef,
    required String body,
    required String clientRequestId,
  }) async {
    calls.add('candidate:$cardRef');
    return const WritingProposal(
        proposalRef: 'prp_candidate',
        artifactId: 'cand_a',
        artifactKind: 'candidate',
        approvalRequired: true);
  }

  @override
  Future<WritingProposalPreview> proposalGet(String proposalRef) async =>
      WritingProposalPreview.fromJson({
        'proposal_ref': proposalRef,
        'approval_preview': {
          'kind': 'candidate',
          'exact_diff': {
            'before': 'Recommendation: hold.\n',
            'after': 'Recommendation: release.\n'
          },
          'stored_scope_receipt_matches': true,
        }
      });

  @override
  Future<Map<String, dynamic>> approve(String proposalRef) async =>
      {'grant_ref': 'gnt_$proposalRef'};

  @override
  Future<Map<String, dynamic>> commit(String proposalRef, String grantRef) async {
    calls.add('commit:$proposalRef:$grantRef');
    return {'event_head_sha256': 'h2'};
  }

  @override
  Future<WritingProposal> prepareDecision({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String decision,
    String? candidateRef,
    String? sectionRef,
    String? toRevisionRef,
    String? reason,
    required String clientRequestId,
  }) async {
    calls.add('decision:$decision:$candidateRef');
    return const WritingProposal(
        proposalRef: 'prp_hold',
        artifactId: 'dec_a',
        artifactKind: 'decision',
        approvalRequired: true);
  }

  @override
  Future<WritingProposal> prepareExport({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String outRef,
    required String clientRequestId,
  }) async {
    calls.add('export:$outRef');
    return const WritingProposal(
        proposalRef: 'prp_export',
        artifactId: 'wexp_a',
        artifactKind: 'export',
        approvalRequired: true);
  }

  @override
  Future<WritingProposal> prepareInit({required Map<String, dynamic> brief,
    required Map<String, dynamic> sourcePacket,
    required String clientRequestId}) async => throw UnimplementedError();

  @override
  Future<WritingProposal> prepareSection({required String journeyRef,
    required String expectedEventHead, required Map<String, dynamic> section,
    required String clientRequestId}) async => throw UnimplementedError();

  @override
  Future<WritingProposal> prepareRevision({required String journeyRef,
    required String expectedEventHead, required String projectRef,
    required String sectionRef, required String body,
    required String clientRequestId}) async => throw UnimplementedError();

  @override
  Future<WritingProposal> prepareDiagnose({required String journeyRef,
    required String expectedEventHead, required String projectRef,
    required String revisionRef, required String clientRequestId}) async =>
      throw UnimplementedError();

  @override
  Future<WritingProposal> prepareCard({required String journeyRef,
    required String expectedEventHead, required Map<String, dynamic> card,
    required String clientRequestId}) async => throw UnimplementedError();
}

WritingProjectView _project() => WritingProjectView.fromJson({
      'project_ref': 'wpr_a',
      'journey_ref': 'jrn_a',
      'event_head_sha256': 'h1',
      'source_packet': {
        'source_packet_ref': 'packet',
        'sources': [
          {'source_id': 'src_receipt', 'title': 'Receipt'}
        ],
        'does_not_prove': []
      },
      'sections': [
        {
          'section_ref': 'sec_recommendation',
          'heading': 'Recommendation',
          'current_revision_ref': 'rev_a',
          'current_body': 'Recommendation: hold.\n',
        }
      ],
      'cards': [
        {'card_ref': 'card_a', 'problem': 'Decision is stale.'}
      ],
      'candidates': [
        {'candidate_ref': 'cand_a', 'card_ref': 'card_a'}
      ],
      'diagnostics': [],
      'decisions': [],
      'reviews': [],
      'exports': [],
      'does_not_prove': []
    });
