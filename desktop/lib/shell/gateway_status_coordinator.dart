// gateway_status_coordinator.dart -- owns the engine connection loop for
// the shell: the typed status probe, the lane/world reads, and the
// start/probe/install actions. The shell renders; this coordinates.
import 'dart:async';

import 'package:flutter/foundation.dart';

import '../client/gateway_client.dart';
import '../models/connection_state.dart';
import '../models/gateway_models.dart';
import '../models/lane_readiness.dart';
import '../services/gateway_status.dart';

class GatewayStatusCoordinator extends ChangeNotifier {
  GatewayStatusCoordinator({
    required this.client,
    required this.status,
    required this.startEngine,
    this.onOrphanStart,
    this.onReady,
    this.autoStartEngine,
  });

  final GatewayClient client;
  final GatewayStatusService? status;
  final Future<String?> Function() startEngine;
  final Future<String?> Function()? autoStartEngine;

  /// Called when an engine start succeeded after this coordinator was
  /// disposed: the shell is gone, so the owned process must be stopped
  /// before the completion is otherwise dropped.
  final VoidCallback? onOrphanStart;
  final Future<void> Function()? onReady;

  bool alive = false;
  ConnectionStatus connection = ConnectionStatus.starting;
  String message = 'connecting…';
  String? startError;
  LaneRoster? roster;
  WorldDoc? world;

  Timer? _timer;
  bool _disposed = false;
  bool _polling = false;
  bool _autoStartConsidered = false;

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }

  void beginPolling() {
    unawaited(poll());
    _timer =
        Timer.periodic(const Duration(seconds: 5), (_) => unawaited(poll()));
  }

  void disposePolling() {
    _timer?.cancel();
  }

  Future<void> poll() async {
    if (_disposed || _polling) return;
    _polling = true;
    try {
      await _poll();
    } finally {
      _polling = false;
    }
  }

  Future<void> _poll() async {
    final wasAlive = alive;
    final service = status;
    if (service == null) {
      // Hand-built dependencies (tests): the legacy liveness check.
      final live = await client.isAlive();
      if (_disposed) return;
      alive = live;
      connection = live ? connection : ConnectionStatus.offline;
      message = live ? message : ConnectionStatus.offline.detail;
      if (live && !wasAlive) await onReady?.call();
      if (live) await _load();
      if (!_disposed) notifyListeners();
      return;
    }
    final result = await service.probe();
    if (_disposed) return;
    final mayAutoStart =
        !_autoStartConsidered && service.localEngineUnavailable;
    _autoStartConsidered = true;
    alive = result.alive;
    connection = result;
    message = result.detail;
    if (mayAutoStart && autoStartEngine != null) {
      await _startBundledOnce();
      return;
    }
    if (result.alive && !wasAlive) await onReady?.call();
    if (result.alive) await _load();
    if (!_disposed) notifyListeners();
  }

  Future<void> _startBundledOnce() async {
    message = 'starting bundled engine…';
    connection = ConnectionStatus.starting;
    notifyListeners();
    if (_disposed) return;
    String? error;
    try {
      error = await autoStartEngine!();
    } catch (_) {
      error =
          'The bundled engine could not be started. Use Start engine to retry.';
    }
    if (_disposed) {
      if (error == null) onOrphanStart?.call();
      return;
    }
    startError = error;
    if (error != null) {
      connection = ConnectionStatus.offline;
      message = 'engine offline';
    }
    // Process creation is not readiness. The next status poll determines it
    // and triggers the existing read-only Journey recovery on a ready edge.
    notifyListeners();
  }

  Future<void> _load() async {
    if (_disposed) return;
    try {
      final nextRoster = await client.laneRoster();
      if (_disposed) return;
      final nextWorld = await client.projectedWorld();
      if (_disposed) return;
      roster = nextRoster;
      world = nextWorld;
      startError = null;
      message = laneReadinessDetail(nextRoster.nLanes, nextRoster.byStatus);
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
      final result = await client.laneRoster(probe: true);
      if (_disposed) return;
      roster = result;
      message = laneReadinessDetail(result.nLanes, result.byStatus,
          probeRequested: true);
    } catch (error) {
      if (_disposed) return;
      message = 'probe failed: $error';
    }
    if (!_disposed) notifyListeners();
  }

  Future<Map<String, dynamic>> installLane(String name) async {
    final result = await client.installLane(name);
    await probeLanes();
    return result;
  }
}
