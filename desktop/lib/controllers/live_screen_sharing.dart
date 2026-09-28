import 'package:flutter/foundation.dart';

import '../client/gateway_client.dart';
import '../client/live_screen_recovery.dart';
import '../models/live_screen_models.dart';
import '../models/live_screen_operation.dart';
import 'gateway_operation_controller.dart';
import 'live_screen_controller.dart';

typedef ScreenAuthorizer
    = Future<GatewayAuthorizationOutcome<Map<String, dynamic>>> Function(
        GatewayOperation operation,
        GatewayOperationSupplier current,
        Future<Map<String, dynamic>> Function(Map<String, dynamic>) dispatch);

enum LiveScreenSessionOrigin { localStart, recovered }

/// Shell-owned capture lifecycle. Navigation never disposes the sharing handle.
class LiveScreenSharing extends ChangeNotifier {
  LiveScreenSharing(this.client) : feed = LiveScreenController(client) {
    feed.addListener(_feedChanged);
  }
  final GatewayClient client;
  final LiveScreenController feed;
  List<LiveScreenSource> sources = const [];
  Set<String> selected = const {};
  String? sessionId, error;
  LiveScreenSessionOrigin? _sessionOrigin;
  LiveScreenSessionOrigin? get sessionOrigin =>
      hasSession ? _sessionOrigin : null;
  String? boundDestination, boundModel;
  String? get bodySessionRef => _bodySession;
  bool busy = false, loading = false, _disposed = false;
  bool uncertainOpen = false;
  int _serial = 0;
  String? _bodySession;
  Map<String, dynamic>? _pendingBinding;
  bool get hasSession => sessionId != null;
  bool get hasUnresolvedCapture => hasSession || uncertainOpen;
  String _requestId() =>
      'screen-${DateTime.now().microsecondsSinceEpoch}-${++_serial}';

  Future<void> refreshSources() async {
    if (loading || _disposed) return;
    loading = true;
    _notify();
    try {
      final result = await client.liveScreenSources();
      if (_disposed) return;
      sources = List.unmodifiable(result);
      if (!hasUnresolvedCapture) {
        selected = Set.unmodifiable(selected
            .where((id) => sources.any((s) => s.id == id && s.available)));
      }
      error = null;
    } catch (_) {
      if (!_disposed) error = 'Capture sources could not be read.';
    } finally {
      loading = false;
      _notify();
    }
  }

  void select(Set<String> value) {
    if (hasUnresolvedCapture || busy || _disposed) return;
    selected = Set.unmodifiable(
        value.where((id) => sources.any((s) => s.id == id && s.available)));
    _notify();
  }

  Future<void> start(ScreenAuthorizer authorize,
      {required String? Function() destination,
      required String? Function() model}) async {
    if (hasUnresolvedCapture || busy || _disposed) return;
    final request = _requestId();
    _bodySession = 'studio-$request';
    GatewayOperation? current() {
      final route = destination(), selectedModel = model();
      if (_disposed || hasSession || route == null || selectedModel == null) {
        return null;
      }
      try {
        return openLiveScreenOperation(
            requestId: request,
            bodySessionRef: _bodySession!,
            instrumentRef: 'screen',
            sourceIds: selected.toList()..sort(),
            destination: route,
            model: selectedModel,
            startImmediately: true);
      } on ArgumentError {
        return null;
      }
    }

    final operation = current();
    if (operation == null) {
      error = 'Select capture sources and an exact model in Rowan first.';
      _notify();
      return;
    }
    busy = true;
    error = null;
    _notify();
    try {
      final outcome = await authorize(operation, current, (body) async {
        _pendingBinding = {
          for (final key in [
            'body_session_ref',
            'instrument_ref',
            'destination',
            'model',
            'delivery_mode'
          ])
            key: body[key],
          'sources': [
            for (final row in body['sources'] as List)
              {'source_id': row['source_id']}
          ],
        };
        uncertainOpen = true;
        final status = await client.liveScreenControl(body);
        // Keep the handle even if the subsequent status/event read fails.
        sessionId = status['session_id'] as String;
        _sessionOrigin = LiveScreenSessionOrigin.localStart;
        uncertainOpen = false;
        _pendingBinding = null;
        boundDestination = status['destination'] as String;
        boundModel = status['model'] as String;
        if (!_disposed) await feed.connect(sessionId!);
        return status;
      });
      if (outcome.denied) error = 'Screen sharing was not approved.';
      if (outcome.failure != null) {
        error = 'Screen sharing could not be approved.';
      }
    } catch (_) {
      error = uncertainOpen
          ? 'Capture may have started. Recover the session before sharing again.'
          : 'Screen sharing could not be confirmed.';
    } finally {
      busy = false;
      _notify();
    }
  }

  Future<void> control(String action, ScreenAuthorizer authorize) async {
    final id = sessionId;
    if (id == null || busy || _disposed) return;
    if (action == 'stop' || action == 'pause') {
      await _revoke(id, action);
      return;
    }
    final request = _requestId();
    GatewayOperation? current() => _disposed || sessionId != id
        ? null
        : controlLiveScreenOperation(
            requestId: request, sessionId: id, control: action);
    final operation = current()!;
    busy = true;
    error = null;
    _notify();
    try {
      final result = await authorize(operation, current, (body) async {
        final status = await client.liveScreenControl(body);
        if (!_disposed) {
          feed.applyControlStatus(status);
          if (action == 'stop') sessionId = null;
        }
        return status;
      });
      if (result.denied) error = 'Screen control was not approved.';
      if (result.failure != null) {
        error = 'Screen control could not be approved.';
      }
    } catch (_) {
      error = 'Capture state is unknown. Retry Stop sharing.';
    } finally {
      busy = false;
      _notify();
    }
  }

  Future<void> _revoke(String id, String action) async {
    busy = true;
    error = null;
    _notify();
    try {
      final status = await client.revokeLiveScreen(id, action);
      if (_disposed || sessionId != id) return;
      feed.applyControlStatus(status);
      if (action == 'stop') sessionId = null;
    } catch (_) {
      error = 'Capture state is unknown. Retry Stop sharing.';
    } finally {
      busy = false;
      _notify();
    }
  }

  Future<void> reconnect() async {
    final id = sessionId;
    if (id != null && !busy && !_disposed) await feed.connect(id);
  }

  Future<void> recover() async {
    final binding = _pendingBinding;
    if (!uncertainOpen || binding == null || busy || _disposed) return;
    busy = true;
    error = null;
    _notify();
    try {
      final status = await recoverLiveScreenSession(client, binding);
      if (_disposed) return;
      if (status == null) {
        error =
            'The share has not been located yet. Capture may still be starting. Retry recovery.';
        return;
      }
      boundDestination = status['destination'] as String;
      boundModel = status['model'] as String;
      _sessionOrigin = LiveScreenSessionOrigin.recovered;
      uncertainOpen = false;
      _pendingBinding = null;
      if (status['state'] == 'stopped') {
        sessionId = null;
      } else {
        sessionId = status['session_id'] as String;
        await feed.connect(sessionId!);
      }
    } catch (_) {
      error =
          'Recovery could not confirm this share. Capture may continue. Retry recovery.';
    } finally {
      busy = false;
      _notify();
    }
  }

  void _feedChanged() {
    if (feed.ended && feed.sessionId == sessionId) sessionId = null;
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    feed.removeListener(_feedChanged);
    feed.dispose();
    super.dispose();
  }
}
