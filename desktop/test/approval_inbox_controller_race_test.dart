import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/approval_inbox_api.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/controllers/approval_inbox_controller.dart';
import 'package:flywheel_desktop/models/approval_inbox_models.dart';

const _hashA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _hashB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _reviewA =
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';
const _reviewB =
    'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd';
const _proposalA = 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _proposalB = 'prp_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

void main() {
  test('latest open keeps its selected review after out-of-order reads',
      () async {
    final api = _RaceInboxApi();
    final controller = ApprovalInboxController(api: api, alive: true);
    await controller.refresh();

    final openA = controller.open(controller.items[0]);
    final openB = controller.open(controller.items[1]);
    api.completeRead(_proposalB);
    await openB;
    api.completeRead(_proposalA);
    await openA;

    expect(controller.selectedItem?.proposalRef, _proposalB);
    expect(controller.selectedRead?.proposalRef, _proposalB);

    await controller.approveSelected();
    expect(api.approveCalls, [(_proposalB, _reviewB)]);
  });

  test('late read errors cannot replace the current selected review', () async {
    final api = _RaceInboxApi();
    final controller = ApprovalInboxController(api: api, alive: true);
    await controller.refresh();

    final openA = controller.open(controller.items[0]);
    final openB = controller.open(controller.items[1]);
    api.completeRead(_proposalB);
    await openB;
    api.failRead(_proposalA);
    await openA;

    expect(controller.phase, ApprovalInboxPhase.ready);
    expect(controller.message, isNull);
    expect(controller.selectedItem?.proposalRef, _proposalB);
    expect(controller.selectedRead?.proposalRef, _proposalB);
  });

  test('selection changes while approval is pending do not clear the new row',
      () async {
    final api = _RaceInboxApi();
    final controller = ApprovalInboxController(api: api, alive: true);
    await controller.refresh();

    final openB = controller.open(controller.items[1]);
    api.completeRead(_proposalB);
    await openB;

    api.holdNextApprove();
    final approval = controller.approveSelected();
    expect(api.approveCalls, [(_proposalB, _reviewB)]);

    final openA = controller.open(controller.items[0]);
    api.completeRead(_proposalA);
    await openA;
    expect(controller.selectedItem?.proposalRef, _proposalA);
    expect(controller.selectedRead?.proposalRef, _proposalA);

    api.completeApprove();
    await approval;

    expect(controller.items.map((item) => item.proposalRef), [_proposalA]);
    expect(controller.selectedItem?.proposalRef, _proposalA);
    expect(controller.selectedRead?.proposalRef, _proposalA);
  });
}

final class _RaceInboxApi implements ApprovalInboxApi {
  final _reads = <String, Completer<GatewayGrantRead>>{
    _proposalA: Completer<GatewayGrantRead>(),
    _proposalB: Completer<GatewayGrantRead>(),
  };
  final approveCalls = <(String, String)>[];
  Completer<GatewayGrantApproval>? _approve;

  void completeRead(String proposalRef) {
    _reads[proposalRef]!.complete(_read(proposalRef));
  }

  void failRead(String proposalRef) {
    _reads[proposalRef]!.completeError(
        const GatewayGrantException('INVALID_RESPONSE', 'stale read failed'));
  }

  void holdNextApprove() {
    _approve = Completer<GatewayGrantApproval>();
  }

  void completeApprove() {
    _approve!.complete(_approval());
    _approve = null;
  }

  @override
  Future<GatewayGrantCapabilities> fetchCapabilities() async =>
      GatewayGrantCapabilities.fromJson(const {
        'schema': 'flywheel.gateway-grant-capabilities/v1',
        'reviewed_approval': true,
        'proposal_list': true,
        'proposal_read': true,
        'durable_reject': true,
        'review_max_bytes': 32768,
      });

  @override
  Future<GatewayGrantList> listPending(
          {int limit = 25, String? cursor}) async =>
      GatewayGrantList.fromJson({
        'schema': 'flywheel.gateway-grant-list/v1',
        'server_time': '2026-09-07T00:00:00Z',
        'state': 'pending',
        'items': [_item(_proposalA), _item(_proposalB)],
        'next_cursor': null,
        'index_complete': true,
        'list_status': 'complete',
        'coverage_scope': 'maintained_index',
        'recovery_required': null,
        'decided_recent_window_seconds': 86400,
        'inspected_index_rows': 2,
        'record_reads': 2,
      });

  @override
  Future<GatewayGrantRead> readProposal(String proposalRef) =>
      _reads[proposalRef]!.future;

  @override
  Future<GatewayGrantApproval> approveReviewed(
      String proposalRef, String reviewSha256) {
    approveCalls.add((proposalRef, reviewSha256));
    return _approve?.future ?? Future.value(_approval());
  }

  @override
  Future<GatewayGrantRejection> rejectProposal(
          String proposalRef, String recordSha256) async =>
      GatewayGrantRejection.fromJson({
        'schema': 'flywheel.gateway-grant-rejection/v1',
        'proposal_ref': proposalRef,
        'proposal_state': 'rejected',
        'record_sha256': recordSha256,
      });

  @override
  Future<ActiveWorkSnapshot> activeWorkSnapshot() async =>
      const ActiveWorkSnapshot(items: []);
}

Map<String, Object?> _item(String proposalRef) {
  final isA = proposalRef == _proposalA;
  return {
    'schema': 'flywheel.gateway-grant-list-item/v1',
    'proposal_ref': proposalRef,
    'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'proposal_state': 'prepared',
    'derived_state': 'pending',
    'record_sha256': isA ? _hashA : _hashB,
    'expires_at': '2026-09-07T00:02:00Z',
    'operation_ref': isA
        ? 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        : 'op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    'review_available': true,
    'review_sha256': isA ? _reviewA : _reviewB,
    'summary': {'schema': 'flywheel.gateway-grant-summary/v1'},
  };
}

GatewayGrantRead _read(String proposalRef) {
  final isA = proposalRef == _proposalA;
  return GatewayGrantRead.fromJson({
    'schema': 'flywheel.gateway-grant-read/v1',
    'server_time': '2026-09-07T00:00:00Z',
    'proposal_state': 'prepared',
    'derived_state': 'pending',
    'record_sha256': isA ? _hashA : _hashB,
    'review_available': true,
    'review': {
      'schema': 'flywheel.gateway-grant-review/v1',
      'proposal_ref': proposalRef,
      'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'record_sha256': isA ? _hashA : _hashB,
      'review_sha256': isA ? _reviewA : _reviewB,
      'operation_ref': isA
          ? 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
          : 'op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
      'action': 'plugin.probe',
      'journey_ref': 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'expected_event_head': isA ? _hashA : _hashB,
      'client_request_id': isA ? 'request-a' : 'request-b',
      'destination': {'kind': 'plugin', 'ref': 'gather'},
      'tool': 'plugin.probe',
      'scopes': ['exec'],
      'data_refs': <String>[],
      'credential_refs': <String>[],
      'execution_plan_sha256': isA ? _hashA : _hashB,
      'operation_sha256': isA ? _hashA : _hashB,
      'arguments_sha256': isA ? _hashA : _hashB,
      'operation': {'name': 'gather'},
      'expires_at': '2026-09-07T00:02:00Z',
    },
  });
}

GatewayGrantApproval _approval() => GatewayGrantApproval.fromJson(const {
      'schema': 'flywheel.operation-grant-approval/v1',
      'grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'expires_at': '2026-09-07T00:02:00Z',
    });
