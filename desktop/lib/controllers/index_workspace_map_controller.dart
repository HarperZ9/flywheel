import 'dart:async';

import 'package:flutter/foundation.dart';

import '../client/index_workspace_map_api.dart';
import '../models/index_workspace_map.dart';

final class IndexWorkspaceMapController extends ChangeNotifier {
  final IndexWorkspaceMapApi _api;
  final bool _poll;
  final Duration _pollInterval;
  int _generation = 0;
  Timer? _pollTimer;
  bool _disposed = false;
  String? _root;
  Map<String, dynamic>? _summary;
  IndexWorkspaceMapJob? _job;
  bool _busy = false;
  String? _message;

  IndexWorkspaceMapController({
    required IndexWorkspaceMapApi api,
    bool poll = true,
    Duration pollInterval = const Duration(seconds: 2),
  })  : _api = api,
        _poll = poll,
        _pollInterval = pollInterval;

  String? get root => _root;
  Map<String, dynamic>? get summary => _summary;
  IndexWorkspaceMapJob? get job => _job;
  bool get busy => _busy;
  String? get message => _message;

  Future<void> open(String root) async {
    final generation = ++_generation;
    _pollTimer?.cancel();
    _root = root;
    _summary = null;
    _job = null;
    _busy = true;
    _message = null;
    _notify();
    await Future.wait([
      _loadSummary(root, generation),
      _recoverOrStart(root, generation),
    ]);
    if (_matches(root, generation)) {
      _busy = false;
      _notify();
    }
  }

  void detach() {
    _generation++;
    _pollTimer?.cancel();
    _root = null;
    _summary = null;
    _job = null;
    _busy = false;
    _message = null;
    _notify();
  }

  Future<void> refreshStatus() async {
    final root = _root;
    if (root == null) return;
    final generation = _generation;
    await _accept(root, generation, _api.status(root, jobId: _job?.jobId));
  }

  Future<void> updateWorkspaceMap() async {
    final root = _root;
    if (root == null) return;
    final generation = ++_generation;
    _pollTimer?.cancel();
    _summary = null;
    _busy = true;
    _message = null;
    _notify();
    await Future.wait([
      _loadSummary(root, generation),
      _accept(root, generation, _api.start(root)),
    ]);
    if (_matches(root, generation)) {
      _busy = false;
      _notify();
    }
  }

  Future<void> cancel() async {
    final root = _root;
    final jobId = _job?.jobId;
    if (root == null || jobId == null || jobId.isEmpty) return;
    await _accept(root, _generation, _api.cancel(root, jobId: jobId));
  }

  Future<void> resume() async {
    final root = _root;
    final jobId = _job?.jobId;
    if (root == null) return;
    await _accept(root, _generation, _api.resume(root, jobId: jobId));
  }

  Future<void> retrieveResult() async {
    final root = _root;
    final jobId = _job?.jobId;
    if (root == null) return;
    await _accept(root, _generation, _api.result(root, jobId: jobId));
  }

  Future<void> _loadSummary(String root, int generation) async {
    try {
      final value = await _api.summary(root);
      if (_matches(root, generation)) {
        _summary = value;
        _notify();
      }
    } catch (e) {
      if (_matches(root, generation)) _setMessage('summary: $e');
    }
  }

  Future<void> _recoverOrStart(String root, int generation) async {
    try {
      var value = await _api.status(root);
      if (value.errorType == 'NO_JOB_FOR_ROOT') {
        value = await _api.start(root);
      }
      if (_matches(root, generation)) _setJob(value);
    } catch (e) {
      if (_matches(root, generation)) _setMessage('workspace map: $e');
    }
  }

  Future<void> _accept(
    String root,
    int generation,
    Future<IndexWorkspaceMapJob> future,
  ) async {
    try {
      final value = await future;
      if (_matches(root, generation)) _setJob(value);
    } catch (e) {
      if (_matches(root, generation)) _setMessage('$e');
    }
  }

  void _setJob(IndexWorkspaceMapJob value) {
    _job = value;
    _message = value.message ?? value.errorType;
    _schedulePoll(value);
    _notify();
  }

  void _setMessage(String value) {
    _message = value;
    _notify();
  }

  void _schedulePoll(IndexWorkspaceMapJob value) {
    _pollTimer?.cancel();
    if (!_poll || !value.active) return;
    _pollTimer = Timer(_pollInterval, () => unawaited(refreshStatus()));
  }

  bool _matches(String root, int generation) =>
      !_disposed && _generation == generation && _root == root;

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _pollTimer?.cancel();
    super.dispose();
  }
}
