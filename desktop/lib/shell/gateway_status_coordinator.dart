// gateway_status_coordinator.dart -- owns the engine connection loop for
// the shell: the typed status probe, the lane/world reads, and the
// start/probe/install actions. The shell renders; this coordinates.
import 'dart:async';

import 'package:flutter/foundation.dart';

import '../client/gateway_client.dart';
import '../models/connection_state.dart';
import '../models/gateway_models.dart';
import '../services/gateway_status.dart';

class GatewayStatusCoordinator extends ChangeNotifier {
  GatewayStatusCoordinator({
    required this.client,
    required this.status,
    required this.startEngine,
    this.onOrphanStart,
  });

  final GatewayClient client;
  final GatewayStatusService? status;
  final Future<String?> Function() startEngine;

  /// Called when an engine start succeeded after this coordinator was
  /// disposed: the shell is gone, so the owned process must be stopped
  /// before the completion is otherwise dropped.
  final VoidCallback? onOrphanStart;

  bool alive = false;
  ConnectionStatus connection = ConnectionStatus.starting;
  String message = 'connecting…';
  String? startError;
  LaneRoster? roster;
  WorldDoc? world;

  Timer? _timer;
  bool _disposed = false;

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }

  void beginPolling() {
    unawaited(poll());
    _timer = Timer.periodic(const Duration(seconds: 5),
        (_) => unawaited(poll()));
  }

  void disposePolling() {
    _timer?.cancel();
  }

  Future<void> poll() async {
    if (_disposed) return;
    final service = status;
    if (service == null) {
      // Hand-built dependencies (tests): the legacy liveness check.
      final live = await client.isAlive();
      if (_disposed) return;
      alive = live;
      connection = live ? connection : ConnectionStatus.offline;
      message = live ? message : ConnectionStatus.offline.detail;
      if (live) await _load();
      if (!_disposed) notifyListeners();
      return;
    }
    final result = await service.probe();
    if (_disposed) return;
    alive = result.alive;
    connection = result;
    message = result.detail;
    if (result.alive) await _load();
    if (!_disposed) notifyListeners();
  }

  Future<void> _load() async {
    try {
      final nextRoster = await client.laneRoster();
      final nextWorld = await client.projectedWorld();
      if (_disposed) return;
      roster = nextRoster;
      world = nextWorld;
      startError = null;
      message =
          '${nextRoster.byStatus['live'] ?? 0}/${nextRoster.nLanes} lanes live';
    } catch (error) {
      if (_disposed) return;
      connection = ConnectionStatus.typed(ConnectionPhase.degraded,
          lanesLive: connection.lanesLive,
          lanesTotal: connection.lanesTotal,
          detail: 'lanes unreadable · degraded');
      message = 'error: $error';
    }
    if (!_disposed) notifyListeners();
  }

  Future<void> start() async {
    if (_disposed) return;
    message = 'starting engine…';
    connection = ConnectionStatus.starting;
    notifyListeners();
    final error = await startEngine();
    if (error == null && _disposed) {
      onOrphanStart?.call();
      return;
    }
    if (_disposed) return;
    startError = error;
    if (error != null) {
      alive = false;
      message = 'engine offline';
      notifyListeners();
      return;
    }
    await Future<void>.delayed(const Duration(seconds: 2));
    await poll();
  }

  Future<void> probeLanes() async {
    if (_disposed) return;
    message = 'probing lanes…';
    notifyListeners();
    try {
      roster = await client.laneRoster(probe: true);
    } catch (error) {
      if (_disposed) return;
      message = 'probe failed: $error';
    }
    await poll();
  }

  Future<Map<String, dynamic>> installLane(String name) async {
    final result = await client.installLane(name);
    await probeLanes();
    return result;
  }
}
