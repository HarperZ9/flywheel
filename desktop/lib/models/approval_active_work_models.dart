import 'evidence_state.dart';

enum ActiveWorkKind { active, terminal, unknown }

const _activeStatuses = {
  'active',
  'in_progress',
  'queued',
  'running',
  'starting',
  'started',
};
const _terminalStatuses = {
  'cancelled',
  'canceled',
  'complete',
  'completed',
  'done',
  'error',
  'failed',
  'sealed',
  'tampered',
  'timed_out',
  'timeout',
  'unreadable',
};
const _successfulTerminalStatuses = {'complete', 'completed', 'done', 'sealed'};

final class ActiveWorkItem {
  final String runId, status;
  final ActiveWorkKind kind;

  const ActiveWorkItem(this.runId, this.status, this.kind);

  String get label => status.isEmpty
      ? runId
      : [status, runId].where((v) => v.isNotEmpty).join(' ');

  String get verdict => switch (kind) {
        ActiveWorkKind.active => 'live',
        ActiveWorkKind.terminal =>
          _successfulTerminalStatuses.contains(status.toLowerCase())
              ? 'verified'
              : 'drift',
        ActiveWorkKind.unknown => 'unverifiable',
      };

  static ActiveWorkItem? fromRelay(Object? raw) {
    if (raw is! Map) return null;
    final runId = _safe('${raw['run_id'] ?? raw['id'] ?? ''}');
    final status = _safe('${raw['status'] ?? ''}').toLowerCase();
    if (runId.isEmpty && status.isEmpty) return null;
    return ActiveWorkItem(runId, status, _kind(status));
  }

  static ActiveWorkKind _kind(String status) {
    if (_activeStatuses.contains(status)) return ActiveWorkKind.active;
    if (_terminalStatuses.contains(status)) return ActiveWorkKind.terminal;
    return ActiveWorkKind.unknown;
  }

  static String _safe(String value) =>
      value.isNotEmpty && isSafePublicText(value) ? value : '';
}

final class ActiveWorkSnapshot {
  final List<ActiveWorkItem> items;
  final String? unavailableReason;

  const ActiveWorkSnapshot({required this.items}) : unavailableReason = null;
  const ActiveWorkSnapshot.unavailable(this.unavailableReason)
      : items = const [];

  bool get unavailable => unavailableReason != null;
  List<ActiveWorkItem> get active => _ofKind(ActiveWorkKind.active);
  List<ActiveWorkItem> get terminal => _ofKind(ActiveWorkKind.terminal);
  List<ActiveWorkItem> get unknown => _ofKind(ActiveWorkKind.unknown);

  List<ActiveWorkItem> _ofKind(ActiveWorkKind kind) =>
      List.unmodifiable(items.where((item) => item.kind == kind));
}
