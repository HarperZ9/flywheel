import 'dart:async';

import 'package:flutter/foundation.dart';

import '../client/gateway_client.dart';
import '../models/live_screen_models.dart';

/// Observes a gateway-owned session; never creates capture or provider authority.
/// One pending preview read coalesces later frames instead of queuing image work.
class LiveScreenController extends ChangeNotifier {
  LiveScreenController(this.client);
  final GatewayClient client;
  ScreenCaptureState state = ScreenCaptureState.stopped;
  String? error, sessionId, viewedSource;
  String? _destination, _model;
  Set<String> _sourceIds = const {};
  final _latest = <String, LiveScreenFrame>{};
  final _history = <LiveScreenFrame>[];
  final _deliveries = <String, LiveScreenDelivery>{};
  LiveScreenFrame? previewFrame;
  Uint8List? previewBytes;
  StreamSubscription<Map<String, dynamic>>? _subscription;
  int _generation = 0;
  int _previewEpoch = 0;
  bool _reading = false, _disposed = false, _ended = false;

  Set<String> get sourceIds => Set.unmodifiable(_sourceIds);
  bool get ended => _ended;
  Future<void> connect(String id) => observe(id, client.liveScreenEvents(id));
  LiveScreenDelivery? get delivery => _deliveries[viewedSource];
  LiveScreenFrame? get deliveredFrame {
    final receipt = delivery;
    if (receipt == null) return null;
    for (final frame in _history.reversed) {
      if (receipt.matches(frame)) return frame;
    }
    return null;
  }

  Future<void> observe(String id, Stream<Map<String, dynamic>> events) async {
    final generation = ++_generation;
    await _subscription?.cancel();
    _subscription = null;
    if (sessionId != id) _reset();
    state = ScreenCaptureState.starting;
    _notify();
    try {
      final status = await client.liveScreenStatus(id);
      if (_disposed || generation != _generation) return;
      final sources = status['source_ids'];
      final destination = status['destination'];
      final model = status['model'];
      if (status['session_id'] != id ||
          destination is! String ||
          destination.isEmpty ||
          destination.length > 256 ||
          model is! String ||
          model.isEmpty ||
          model.length > 256 ||
          sources is! List ||
          sources.isEmpty ||
          sources.length > 16 ||
          sources.any((v) => v is! String || v.isEmpty) ||
          sources.toSet().length != sources.length) {
        throw const FormatException('Invalid screen session');
      }
      sessionId = id;
      _destination = destination;
      _model = model;
      _sourceIds = Set.unmodifiable(sources.cast<String>());
      viewedSource = _sourceIds.first;
      _setState(status['state']);
      _subscription = events.listen((event) {
        if (!_disposed && generation == _generation) _event(event);
      }, onError: (Object _) {
        if (!_disposed && generation == _generation) disconnect();
      }, onDone: () {
        if (!_disposed &&
            generation == _generation &&
            state != ScreenCaptureState.stopped) {
          disconnect();
        }
      });
      _notify();
    } catch (_) {
      if (!_disposed && generation == _generation) disconnect();
    }
  }

  void viewSource(String id) {
    if (!_sourceIds.contains(id) || _disposed) return;
    viewedSource = id;
    previewFrame = null;
    previewBytes = null;
    _notify();
    unawaited(_loadLatest());
  }

  /// Only used with a validated control response for this exact session.
  void applyControlStatus(Map<String, dynamic> status) {
    if (_disposed || status['session_id'] != sessionId) return;
    _setState(status['state']);
    _notify();
  }

  void _event(Map<String, dynamic> event) {
    if (event['session_id'] != sessionId) return;
    switch (event['event']) {
      case 'screen.frame':
        if (state != ScreenCaptureState.running) return;
        final frame = LiveScreenFrame.fromJson(event);
        if (!frame.valid || !_sourceIds.contains(frame.sourceId)) return;
        final old = _latest[frame.sourceId];
        if (old != null && frame.sequence <= old.sequence) return;
        _latest[frame.sourceId] = frame;
        _history.add(frame);
        while (_history.length > 12 * _sourceIds.length) {
          _history.removeAt(0);
        }
        unawaited(_loadLatest());
      case 'screen.delivery':
        if (state != ScreenCaptureState.running) return;
        final receipt = LiveScreenDelivery.fromJson(event);
        if (!receipt.valid ||
            !_sourceIds.contains(receipt.sourceId) ||
            receipt.modelRoute != _destination ||
            receipt.model != _model) {
          return;
        }
        final old = _deliveries[receipt.sourceId];
        if (old != null && receipt.sequence <= old.sequence) return;
        _deliveries[receipt.sourceId] = receipt;
      case 'screen.pause':
        _setState('paused');
      case 'screen.stop':
        _setState('stopped');
      case 'screen.session':
        _setState(event['state']);
      case 'screen.error':
        disconnect();
      default:
        return;
    }
    _notify();
  }

  void _setState(Object? value) {
    if (_ended && value != 'disconnected') return;
    if (value == 'stopped') _ended = true;
    state = switch (value) {
      'created' => ScreenCaptureState.stopped,
      'active' => ScreenCaptureState.running,
      'paused' => ScreenCaptureState.paused,
      'stopped' => ScreenCaptureState.stopped,
      _ => ScreenCaptureState.disconnected,
    };
    if (state != ScreenCaptureState.running) {
      ++_previewEpoch;
      previewBytes = null;
      previewFrame = null;
      _latest.clear();
    }
  }

  Future<void> _loadLatest() async {
    if (_reading || _disposed || state != ScreenCaptureState.running) return;
    _reading = true;
    final generation = _generation;
    LiveScreenFrame? requested;
    var retryLatest = false;
    try {
      while (!_disposed &&
          generation == _generation &&
          state == ScreenCaptureState.running) {
        final wanted = _latest[viewedSource];
        if (wanted == null || identical(previewFrame, wanted)) break;
        requested = wanted;
        final epoch = _previewEpoch;
        final bytes = await client.liveScreenPreview(wanted);
        if (_disposed ||
            generation != _generation ||
            state != ScreenCaptureState.running) {
          break;
        }
        if (wanted.sourceId != viewedSource || epoch != _previewEpoch) {
          continue;
        }
        previewFrame = wanted;
        previewBytes = bytes;
        error = null;
        _notify();
      }
    } catch (_) {
      if (!_disposed &&
          generation == _generation &&
          state == ScreenCaptureState.running) {
        if (!identical(_latest[viewedSource], requested)) {
          retryLatest = true;
        } else {
          error = 'Local preview unavailable';
          previewBytes = null;
          previewFrame = null;
          _notify();
        }
      }
    } finally {
      _reading = false;
      if (!_disposed && (generation != _generation || retryLatest)) {
        unawaited(_loadLatest());
      }
    }
  }

  void disconnect() {
    ++_generation;
    unawaited(_subscription?.cancel());
    _subscription = null;
    _setState('disconnected');
    error = 'Screen feed disconnected';
    _notify();
  }

  void _reset() {
    sessionId = null;
    _destination = null;
    _model = null;
    viewedSource = null;
    _sourceIds = const {};
    _latest.clear();
    _history.clear();
    _deliveries.clear();
    previewFrame = null;
    previewBytes = null;
    error = null;
    _ended = false;
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    ++_generation;
    unawaited(_subscription?.cancel());
    _reset();
    super.dispose();
  }
}
