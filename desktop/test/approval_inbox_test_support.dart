import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/approval_inbox_api.dart';
import 'package:flywheel_desktop/models/approval_inbox_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';

const approvalHash =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const defaultProposalRef = 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const proposalRef = defaultProposalRef;
const secondProposalRef = 'prp_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const defaultReviewSha =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const reviewSha = defaultReviewSha;
const secondReviewSha =
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';

Widget wrapInbox(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SizedBox(width: 520, height: 600, child: child)),
    );

Future<void> scrollActionIntoView(WidgetTester tester, String label) async {
  final target = find.text(label);
  for (var attempt = 0; attempt < 5; attempt++) {
    final center = tester.getCenter(target);
    if (center.dy >= 0 && center.dy <= 590) return;
    await tester.drag(find.byType(ListView), const Offset(0, -120));
    await tester.pumpAndSettle();
  }
}

final class FakeInboxApi implements ApprovalInboxApi {
  FakeInboxApi({
    required this.capabilities,
    this.capabilitiesError,
    List<GatewayGrantList>? pages,
    Map<String, GatewayGrantRead>? reads,
    this.activeWork = const ActiveWorkSnapshot(items: []),
  })  : _pages = pages ??
            [
              listPage(items: [listItem()])
            ],
        _reads = reads ?? {proposalRef: GatewayGrantRead.fromJson(readBody())};

  FakeInboxApi.ready({
    String? relayRun,
    List<GatewayGrantList>? pages,
    Map<String, GatewayGrantRead>? reads,
    ActiveWorkSnapshot? activeWork,
  }) : this(
          capabilities: GatewayGrantCapabilities.fromJson(const {
            'schema': 'flywheel.gateway-grant-capabilities/v1',
            'reviewed_approval': true,
            'proposal_list': true,
            'proposal_read': true,
            'durable_reject': true,
            'review_max_bytes': 32768,
          }),
          pages: pages,
          reads: reads,
          activeWork: activeWork ??
              (relayRun == null
                  ? const ActiveWorkSnapshot(items: [])
                  : ActiveWorkSnapshot(items: [
                      ActiveWorkItem(relayRun, 'running', ActiveWorkKind.active)
                    ])),
        );

  final GatewayGrantCapabilities capabilities;
  final Object? capabilitiesError;
  final List<GatewayGrantList> _pages;
  final Map<String, GatewayGrantRead> _reads;
  final ActiveWorkSnapshot activeWork;
  final listCursors = <String?>[];
  final readCalls = <String>[];
  final approveCalls = <(String, String)>[];
  final legacyApproveCalls = <String>[];
  final rejectCalls = <(String, String)>[];
  var _pageIndex = 0;

  @override
  Future<GatewayGrantCapabilities> fetchCapabilities() async {
    final error = capabilitiesError;
    if (error != null) throw error;
    return capabilities;
  }

  @override
  Future<GatewayGrantList> listPending({int limit = 25, String? cursor}) async {
    listCursors.add(cursor);
    final index = _pageIndex < _pages.length ? _pageIndex : _pages.length - 1;
    _pageIndex++;
    return _pages[index];
  }

  @override
  Future<GatewayGrantRead> readProposal(String proposalRef) async {
    readCalls.add(proposalRef);
    return _reads[proposalRef] ?? GatewayGrantRead.fromJson(readBody());
  }

  @override
  Future<GatewayGrantApproval> approveReviewed(
      String proposalRef, String reviewSha256) async {
    approveCalls.add((proposalRef, reviewSha256));
    return GatewayGrantApproval.fromJson(const {
      'schema': 'flywheel.operation-grant-approval/v1',
      'grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'expires_at': '2026-09-07T00:02:00Z',
    });
  }

  @override
  Future<GatewayGrantRejection> rejectProposal(
      String proposalRef, String recordSha256) async {
    rejectCalls.add((proposalRef, recordSha256));
    return GatewayGrantRejection.fromJson({
      'schema': 'flywheel.gateway-grant-rejection/v1',
      'proposal_ref': proposalRef,
      'proposal_state': 'rejected',
      'record_sha256': approvalHash,
    });
  }

  @override
  Future<ActiveWorkSnapshot> activeWorkSnapshot() async => activeWork;
}

GatewayGrantList listPage({
  required List<Map<String, Object?>> items,
  String? nextCursor,
  bool indexComplete = true,
  String listStatus = 'complete',
  String coverageScope = 'maintained_index',
  String? recoveryRequired,
}) =>
    GatewayGrantList.fromJson({
      'schema': 'flywheel.gateway-grant-list/v1',
      'server_time': '2026-09-07T00:00:00Z',
      'state': 'pending',
      'items': items,
      'next_cursor': nextCursor,
      'index_complete': indexComplete,
      'list_status': listStatus,
      'coverage_scope': coverageScope,
      'recovery_required': recoveryRequired,
      'decided_recent_window_seconds': 86400,
      'inspected_index_rows': items.length,
      'record_reads': items.length,
    });

Map<String, Object?> listItem({
  String proposalRef = defaultProposalRef,
  String reviewSha = defaultReviewSha,
  bool reviewAvailable = true,
}) =>
    {
      'schema': 'flywheel.gateway-grant-list-item/v1',
      'proposal_ref': proposalRef,
      'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'proposal_state': 'prepared',
      'derived_state': reviewAvailable ? 'pending' : 'review_unavailable',
      'record_sha256': approvalHash,
      'expires_at': '2026-09-07T00:02:00Z',
      'operation_ref': 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'review_available': reviewAvailable,
      if (reviewAvailable) 'review_sha256': reviewSha,
      if (!reviewAvailable) 'unavailable_reason': 'OPERATION_REVIEW_TOO_LARGE',
      'summary': {'schema': 'flywheel.gateway-grant-summary/v1'},
    };

GatewayGrantRead readUnavailable() => GatewayGrantRead.fromJson(const {
      'schema': 'flywheel.gateway-grant-read/v1',
      'server_time': '2026-09-07T00:00:00Z',
      'proposal_state': 'prepared',
      'derived_state': 'review_unavailable',
      'record_sha256': approvalHash,
      'review_available': false,
      'unavailable_reason': 'OPERATION_REVIEW_TOO_LARGE',
    });

Map<String, Object?> readBody() => {
      'schema': 'flywheel.gateway-grant-read/v1',
      'server_time': '2026-09-07T00:00:00Z',
      'proposal_state': 'prepared',
      'derived_state': 'pending',
      'record_sha256': approvalHash,
      'review_available': true,
      'review': {
        'schema': 'flywheel.gateway-grant-review/v1',
        'proposal_ref': proposalRef,
        'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'record_sha256': approvalHash,
        'review_sha256': reviewSha,
        'operation_ref': 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'action': 'plugin.probe',
        'journey_ref': 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'expected_event_head': approvalHash,
        'client_request_id': 'request-1',
        'destination': {'kind': 'plugin', 'ref': 'gather'},
        'tool': 'plugin.probe',
        'scopes': ['exec', 'network', 'plugin'],
        'data_refs': <String>[],
        'credential_refs': ['cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
        'execution_plan_sha256': approvalHash,
        'operation_sha256': approvalHash,
        'arguments_sha256': approvalHash,
        'operation': {
          'name': 'gather',
          'nested': {'flag': true},
          'credential_refs': ['cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
        },
        'expires_at': '2026-09-07T00:02:00Z',
      },
    };
