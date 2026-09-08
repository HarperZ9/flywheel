import 'package:flutter/foundation.dart';

import '../client/approval_inbox_api.dart';
import '../client/gateway_grants.dart';
import '../models/approval_inbox_models.dart';

enum ApprovalInboxPhase { idle, loading, ready, upgradeRequired, acting, error }

final class ApprovalInboxController extends ChangeNotifier {
  final ApprovalInboxApi api;
  bool alive;
  ApprovalInboxPhase phase = ApprovalInboxPhase.idle;
  GatewayGrantCapabilities? capabilities;
  List<GatewayGrantListItem> _items = const [];
  ActiveWorkSnapshot activeWork = const ActiveWorkSnapshot(items: []);
  GatewayGrantListItem? selectedItem;
  GatewayGrantRead? selectedRead;
  String? nextCursor;
  bool indexComplete = true;
  String listStatus = 'complete';
  String recoveryRequired = '';
  int decidedRecentWindowSeconds = 0, inspectedIndexRows = 0, recordReads = 0;
  String? message;
  bool loadingMore = false, _disposed = false;
  int _readGeneration = 0;
  final _hidden = <String>{};
  ApprovalInboxController({required this.api, required this.alive});
  List<GatewayGrantListItem> get items => List.unmodifiable(
      _items.where((item) => !_hidden.contains(item.proposalRef)));
  bool get canApprove => _selectionBound && selectedRead?.approvable == true;
  bool get canReject => _selectionBound && _selectedRecordSha256.isNotEmpty;
  bool get canLoadMore => nextCursor != null && !loadingMore;
  String? get listCompletenessMessage =>
      indexComplete && listStatus == 'complete' && recoveryRequired.isEmpty
          ? null
          : _listCompletenessMessage(listStatus, recoveryRequired);
  String get _selectedRecordSha256 => selectedRead?.recordSha256 ?? '';
  void setAlive(bool value) {
    if (alive == value) return;
    alive = value;
    if (!alive) {
      _clearSelection();
      phase = ApprovalInboxPhase.idle;
      message = 'Gateway offline';
      notifyListeners();
    }
  }

  Future<void> refresh() async {
    _hidden.clear();
    _clearSelection();
    nextCursor = null;
    _resetListCompleteness();
    await _load(resetMessage: true);
  }

  Future<void> loadMore() async {
    final cursor = nextCursor;
    if (cursor == null || loadingMore) return;
    loadingMore = true;
    notifyListeners();
    try {
      final list = await api.listPending(cursor: cursor);
      if (list.invalidResponse) {
        throw const GatewayGrantException(
            'INVALID_RESPONSE', 'Gateway response was invalid');
      }
      _items = List.unmodifiable([..._items, ...list.items]);
      _applyListCompleteness(list);
      _updateNextCursor(list);
    } on Object catch (error) {
      message = _safeFailure(error);
    } finally {
      loadingMore = false;
      _notify();
    }
  }

  Future<void> open(GatewayGrantListItem item) async {
    final generation = ++_readGeneration;
    selectedItem = item;
    selectedRead = null;
    phase = ApprovalInboxPhase.loading;
    message = null;
    notifyListeners();
    try {
      final read = await api.readProposal(item.proposalRef);
      if (!_isCurrentRead(generation, item.proposalRef)) return;
      if (read.invalidResponse || !_readMatchesItem(item, read)) {
        throw const GatewayGrantException(
            'INVALID_RESPONSE', 'Gateway response was invalid');
      }
      selectedRead = read;
      phase = ApprovalInboxPhase.ready;
    } on Object catch (error) {
      if (!_isCurrentRead(generation, item.proposalRef)) return;
      phase = ApprovalInboxPhase.error;
      message = _safeFailure(error);
    }
    _notify();
  }

  Future<void> approveSelected() async {
    final review = selectedRead?.review;
    if (!canApprove || review == null) return;
    final proposal = review.proposalRef;
    final reviewSha = review.reviewSha256;
    await _act(() async {
      await api.approveReviewed(proposal, reviewSha);
      _finishAction(proposal, 'Approved reviewed proposal');
    });
  }

  Future<void> rejectSelected() async {
    final proposal = selectedItem?.proposalRef;
    final record = _selectedRecordSha256;
    if (!canReject || proposal == null || proposal.isEmpty || record.isEmpty) {
      return;
    }
    await _act(() async {
      await api.rejectProposal(proposal, record);
      _finishAction(proposal, 'Rejected proposal');
    });
  }

  void dismissSelected() {
    final proposal = selectedItem?.proposalRef ?? selectedRead?.proposalRef;
    if (proposal == null || proposal.isEmpty) return;
    _hidden.add(proposal);
    _clearSelection();
    message = 'Dismissed locally';
    notifyListeners();
  }

  Future<void> _load({required bool resetMessage}) async {
    if (!alive) {
      phase = ApprovalInboxPhase.idle;
      message = 'Gateway offline';
      notifyListeners();
      return;
    }
    phase = ApprovalInboxPhase.loading;
    if (resetMessage) message = null;
    notifyListeners();
    try {
      final activeFuture = api.activeWorkSnapshot();
      final caps = await _fetchCapabilities();
      capabilities = caps;
      activeWork = await _safeActive(activeFuture);
      if (!caps.ready) {
        _items = const [];
        nextCursor = null;
        phase = ApprovalInboxPhase.upgradeRequired;
        message = 'upgrade_required: gateway lacks reviewed approval inbox';
        _notify();
        return;
      }
      final list = await api.listPending();
      if (list.invalidResponse) {
        throw const GatewayGrantException(
            'INVALID_RESPONSE', 'Gateway response was invalid');
      }
      _items = list.items;
      _applyListCompleteness(list);
      _updateNextCursor(list);
      phase = ApprovalInboxPhase.ready;
    } on Object catch (error) {
      phase = ApprovalInboxPhase.error;
      message = _safeFailure(error);
    }
    _notify();
  }

  Future<GatewayGrantCapabilities> _fetchCapabilities() async {
    try {
      return await api.fetchCapabilities();
    } on Object catch (error) {
      final failure = gatewayGrantFailure(error);
      if (failure.code == 'NOT_FOUND' || failure.code == 'INVALID_REQUEST') {
        return GatewayGrantCapabilities.fromJson(const {});
      }
      rethrow;
    }
  }

  Future<ActiveWorkSnapshot> _safeActive(
      Future<ActiveWorkSnapshot> future) async {
    try {
      return await future;
    } on Object {
      return const ActiveWorkSnapshot.unavailable(
          'Active work status unavailable');
    }
  }

  void _resetListCompleteness() {
    indexComplete = true;
    listStatus = 'complete';
    recoveryRequired = '';
    decidedRecentWindowSeconds = inspectedIndexRows = recordReads = 0;
  }

  void _applyListCompleteness(GatewayGrantList list) {
    indexComplete = indexComplete && list.indexComplete;
    if (list.listStatus != 'complete' || listStatus == 'complete') {
      listStatus = list.listStatus;
    }
    if (list.recoveryRequired.isNotEmpty) {
      recoveryRequired = list.recoveryRequired;
    }
    decidedRecentWindowSeconds = list.decidedRecentWindowSeconds;
    inspectedIndexRows += list.inspectedIndexRows;
    recordReads += list.recordReads;
  }

  void _updateNextCursor(GatewayGrantList list) {
    nextCursor = list.nextCursor.isEmpty ? null : list.nextCursor;
  }

  Future<void> _act(Future<void> Function() action) async {
    phase = ApprovalInboxPhase.acting;
    message = null;
    notifyListeners();
    try {
      await action();
      phase = ApprovalInboxPhase.ready;
    } on Object catch (error) {
      phase = ApprovalInboxPhase.error;
      message = _safeFailure(error);
    }
    _notify();
  }

  String _safeFailure(Object error) {
    final failure = gatewayGrantFailure(error);
    return '${failure.code}: ${failure.message}';
  }

  bool get _selectionBound {
    final item = selectedItem, read = selectedRead;
    return item != null && read != null && _readMatchesItem(item, read);
  }

  bool _readMatchesItem(GatewayGrantListItem item, GatewayGrantRead read) {
    final record = read.recordSha256;
    if (record.isNotEmpty &&
        item.recordSha256.isNotEmpty &&
        record != item.recordSha256) {
      return false;
    }
    final review = read.review;
    if (review == null) return !read.reviewAvailable && record.isNotEmpty;
    return review.proposalRef == item.proposalRef &&
        (item.reviewSha256.isEmpty || item.reviewSha256 == review.reviewSha256);
  }

  bool _isCurrentRead(int g, String ref) =>
      !_disposed && g == _readGeneration && selectedItem?.proposalRef == ref;

  void _finishAction(String proposal, String success) {
    _hidden.add(proposal);
    if (selectedItem?.proposalRef == proposal) {
      _clearSelection();
    }
    message = success;
  }

  void _clearSelection() {
    _readGeneration++;
    selectedItem = null;
    selectedRead = null;
  }

  String _listCompletenessMessage(String status, String recovery) {
    final detail = recovery.isNotEmpty
        ? 'recovery required: $recovery'
        : switch (status) {
            'legacy_index_required' => 'legacy index required',
            'index_drift' => 'index drift detected',
            'index_mutation_pending' => 'index mutation pending',
            'index_unavailable' => 'index unavailable',
            'recovery_required' => 'recovery required',
            _ => 'index completeness unknown',
          };
    return 'Approval inbox list is recovery-limited for maintained_index: '
        '$detail. Empty results do not prove proposal absence outside it.';
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _readGeneration++;
    super.dispose();
  }
}
