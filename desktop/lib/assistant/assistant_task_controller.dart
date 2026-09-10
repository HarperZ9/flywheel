import 'package:flutter/foundation.dart';
import '../client/assistant_task_api.dart';
import '../models/assistant_task.dart';

// Reads the current gateway's existing run store. No prompts, credentials or
// result bodies are copied to local persistence and recovery never resubmits.
class AssistantTaskController extends ChangeNotifier {
  AssistantTaskController(this.api);
  final AssistantTaskApi api;
  final _tasks = <String, AssistantTask>{};
  final _reading = <String>{};
  final _tracked = <String>{};
  final _revisions = <String, int>{};
  int _revision = 0;
  bool loading = false;
  bool unavailable = false;
  bool _disposed = false;

  List<AssistantTask> get tasks => List.unmodifiable(_tasks.values);

  void submitted(String runId) {
    if (!isAssistantRunRef(runId)) return;
    _put(AssistantTask(runId, AssistantTaskState.submitted));
    _tracked.add(runId);
    _notify();
  }

  Future<void> recover() async {
    if (loading || _disposed) return;
    loading = true;
    final revisions = Map<String, int>.of(_revisions);
    _notify();
    try {
      final recent = await api.recent();
      if (_disposed) return;
      for (final task in recent) {
        if (_revisions[task.runId] == revisions[task.runId]) _put(task);
      }
      unavailable = false;
    } catch (_) {
      if (_disposed) return;
      unavailable = true;
      for (final ref in _tasks.keys.toList()) {
        if (_revisions[ref] == revisions[ref]) _put(AssistantTask.unknown(ref));
      }
    } finally {
      if (!_disposed) {
        loading = false;
        _notify();
      }
    }
  }

  Future<void> refresh(String runId) async {
    if (_disposed || !isAssistantRunRef(runId) || !_reading.add(runId)) return;
    _tracked.add(runId);
    try {
      final task = await api.read(runId);
      if (!_disposed) {
        _put(task.runId == runId ? task : AssistantTask.unknown(runId));
      }
    } catch (_) {
      if (!_disposed) _put(AssistantTask.unknown(runId));
    } finally {
      _reading.remove(runId);
      _notify();
    }
  }

  Future<void> refreshTracked() async {
    for (final ref in _tracked.toList()) {
      if (_disposed) return;
      final task = _tasks[ref];
      if (task == null ||
          task.active ||
          task.state == AssistantTaskState.unknown) {
        await refresh(ref);
      }
    }
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  void _put(AssistantTask task) {
    if (!_tasks.containsKey(task.runId) && _tasks.length >= 64) {
      final oldest = _tasks.keys.first;
      _tasks.remove(oldest);
      _tracked.remove(oldest);
      _revisions.remove(oldest);
    }
    _tasks[task.runId] = task;
    _revisions[task.runId] = ++_revision;
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
