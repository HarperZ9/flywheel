import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import '../services/code_draft_store.dart';
import 'code_buffer_custody.dart';
import 'diff.dart';
import 'workspace.dart' as workspace;
import 'workspace_file_transaction.dart';

typedef OpenFile = workspace.OpenFile;
typedef CodeRecoveryKind = workspace.CodeRecoveryKind;
typedef CodeRecoveryConflict = workspace.CodeRecoveryConflict;
typedef CodeRecoveryOutcome = workspace.CodeRecoveryOutcome;
typedef CodeSessionException = workspace.CodeSessionException;
typedef CodeSessionFailure = workspace.CodeSessionFailure;
typedef CodeLoadFile = workspace.LoadedFile Function(String path);
typedef CodeCompareAndWrite = WorkspaceWriteResult Function(String root,
    String path, String diskSha, String bufferSha, List<int> bytes);

enum CodeSessionPhase { closed, recovering, recoveryBlocked, ready }

final class CodeBufferSession extends ChangeNotifier {
  CodeBufferSession({
    required this.draftStore,
    CodeLoadFile? loadFile,
    CodeCompareAndWrite? compareAndWrite,
    DateTime Function()? now,
  })  : _load = loadFile ?? workspace.loadFile,
        _write = compareAndWrite ?? _defaultWrite,
        _custody = CodeBufferCustody(draftStore),
        _now = now ?? (() => DateTime.now().toUtc());
  final CodeDraftStore draftStore;
  final CodeLoadFile _load;
  final CodeCompareAndWrite _write;
  final CodeBufferCustody _custody;
  final DateTime Function() _now;
  final List<OpenFile> _open = [];
  final Map<String, String> _preRun = {};
  List<FileDiff> _diffs = const [];
  workspace.WorkspaceSessionIo? _io;
  int _active = -1;
  CodeSessionPhase _phase = CodeSessionPhase.closed;
  CodeSessionFailure? _presentationFailure;
  String? _status;
  String? get workspaceRoot => _io?.root;
  int get activeIndex => _active;
  CodeSessionPhase get phase => _phase;
  List<OpenFile> get openFiles => List.unmodifiable(_open);
  List<workspace.CodeRecoveryOutcome> get recoveryOutcomes =>
      List.unmodifiable(_custody.outcomes);
  List<workspace.CodeRecoveryConflict> get conflicts =>
      List.unmodifiable(_custody.conflicts);
  List<FileDiff> get diffs => List.unmodifiable(_diffs);
  workspace.CodeSessionFailure? get failure => _presentationFailure;
  String? get status => _status;
  List<CodeDraft> get drafts => _custody.drafts;
  List<String> get dirtyPaths => _io?.dirtyPaths(_open) ?? const [];
  bool get closeAdmissionReady =>
      _phase == CodeSessionPhase.closed ||
      (_phase == CodeSessionPhase.ready &&
          _open.where((file) => file.dirty).every(_custody.closable));
  void openWorkspace(String root) {
    final candidate = workspace.WorkspaceSessionIo.open(root);
    if (_open.any((file) => file.dirty)) {
      throw const CodeSessionException(CodeSessionFailure.localStore);
    }
    _reset();
    _io = candidate;
    _phase = CodeSessionPhase.recovering;
    notifyListeners();
  }

  List<workspace.CodeRecoveryOutcome> recover() {
    if (_phase != CodeSessionPhase.recovering || _io == null) return const [];
    try {
      final outcomes = _custody.recoverInto(_io!, _open);
      _active = _open.isEmpty ? -1 : _open.length - 1;
      _phase = CodeSessionPhase.ready;
      _presentationFailure = null;
      notifyListeners();
      return outcomes;
    } catch (_) {
      _phase = CodeSessionPhase.recoveryBlocked;
      _presentationFailure = CodeSessionFailure.localStore;
      _status = 'draft recovery required';
      notifyListeners();
      return const [];
    }
  }

  bool retryRecovery() {
    if (_phase != CodeSessionPhase.recoveryBlocked) return false;
    _phase = CodeSessionPhase.recovering;
    return recover().isNotEmpty || _phase == CodeSessionPhase.ready;
  }

  void openFile(String absolutePath) {
    _requireReady();
    _addLoaded(_io!.openWith(absolutePath, _load));
    notifyListeners();
  }

  void selectIndex(int index) {
    if (index < 0 || index >= _open.length) return;
    _active = index;
    notifyListeners();
  }

  void snapshot(String absolutePath) {
    _requireReady();
    final file = _find(absolutePath);
    if (file.readOnly) return;
    final digest = workspace.codeTextSha256(file.controller.text);
    file.dirty = digest != file.diskSha256;
    if (!file.dirty) {
      if (!_deleteJournal(file, allowAbsent: true)) {
        file.dirty = true;
        _presentationFailure = CodeSessionFailure.localStore;
        notifyListeners();
      }
      return;
    }
    file.journalBufferSha256 = null;
    file.journalRecordSha256 = null;
    try {
      final stored = _custody.save(_io!, file, digest, _now().toUtc());
      file
        ..journalBufferSha256 = digest
        ..journalRecordSha256 = stored.recordSha256
        ..journalFailure = null
        ..diskFailure = null;
      if (_open.every((item) => item.journalFailure == null)) {
        _presentationFailure = null;
      }
      _status = 'draft saved';
    } catch (_) {
      file.journalFailure = CodeSessionFailure.localStore;
      _presentationFailure = CodeSessionFailure.localStore;
      _status = 'draft save failed';
    }
    notifyListeners();
  }

  bool save(String absolutePath) {
    if (_phase != CodeSessionPhase.ready) return false;
    final file = _find(absolutePath);
    if (!file.dirty) return true;
    if (file.readOnly && _conflict(file.relativePath) == null) return false;
    final digest = workspace.codeTextSha256(file.controller.text);
    if (!_custody.hasJournal(file) || file.journalBufferSha256 != digest) {
      return false;
    }
    if (!_generationCurrent(file)) return false;
    try {
      final result = _write(_io!.root, file.path, file.diskSha256, digest,
          utf8.encode(file.controller.text));
      if (result.sha256 != digest) {
        throw const WorkspaceFileException(CodeDiskFailure.readbackFailed);
      }
      if (!_deleteJournal(file)) return false;
      file
        ..diskSha256 = digest
        ..dirty = false
        ..readOnly = false
        ..diskFailure = null;
      _custody.removeConflict(file.relativePath);
      _status = 'saved ${file.name}';
      notifyListeners();
      return true;
    } on WorkspaceFileException catch (error) {
      file.diskFailure = error.failure;
      if (error.failure == CodeDiskFailure.changed ||
          error.failure == CodeDiskFailure.missing) {
        _custody.addConflict(_io!, file, error.failure, _load);
      }
      notifyListeners();
      return false;
    }
  }

  bool discard(String absolutePath) {
    if (_phase != CodeSessionPhase.ready) return false;
    final file = _find(absolutePath);
    if (!file.dirty) return true;
    if (!_custody.hasJournal(file) || !_generationCurrent(file)) return false;
    if (!_deleteJournal(file)) return false;
    if (File(file.path).existsSync()) {
      final disk = _io!.openWith(file.path, _load).loaded;
      file
        ..controller.text = disk.content
        ..diskSha256 = disk.sha256
        ..readOnly = disk.readOnly
        ..note = disk.note;
    } else {
      file
        ..controller.clear()
        ..readOnly = true
        ..note = 'file missing';
    }
    file.dirty = false;
    _custody.removeConflict(file.relativePath);
    _status = 'discarded ${file.name}';
    notifyListeners();
    return true;
  }

  bool closeFile(String absolutePath) {
    if (_phase != CodeSessionPhase.ready) return false;
    final index =
        _open.indexWhere((file) => _io!.samePath(file.path, absolutePath));
    if (index < 0) return true;
    if (_open[index].dirty) return false;
    _open.removeAt(index).controller.dispose();
    if (_active >= _open.length) _active = _open.length - 1;
    notifyListeners();
    return true;
  }

  bool closeWorkspace() {
    if (_phase != CodeSessionPhase.ready || _open.any((file) => file.dirty)) {
      return false;
    }
    _reset();
    notifyListeners();
    return true;
  }

  void snapshotOpenFiles() {
    if (_phase == CodeSessionPhase.ready) _io!.snapshot(_open, _preRun);
  }

  void reloadCleanFiles() {
    if (_phase != CodeSessionPhase.ready) return;
    _diffs = _io!.reloadClean(_open, _preRun, _load);
    notifyListeners();
  }

  void report(String? message) {
    _status = message;
    notifyListeners();
  }

  bool _generationCurrent(OpenFile file) {
    try {
      return _custody.generationCurrent(_io!, file) || _blockRecovery();
    } catch (_) {
      return _blockRecovery();
    }
  }

  bool _deleteJournal(OpenFile file, {bool allowAbsent = false}) =>
      _custody.delete(_io!, file, allowAbsent: allowAbsent);

  bool _blockRecovery() {
    _phase = CodeSessionPhase.recoveryBlocked;
    _presentationFailure = CodeSessionFailure.localStore;
    notifyListeners();
    return false;
  }

  void _requireReady() {
    if (_phase != CodeSessionPhase.ready) {
      throw const CodeSessionException(CodeSessionFailure.localStore);
    }
  }

  OpenFile _find(String path) =>
      _open.firstWhere((file) => _io!.samePath(file.path, path),
          orElse: () =>
              throw const CodeSessionException(CodeSessionFailure.invalidPath));
  workspace.CodeRecoveryConflict? _conflict(String path) =>
      _custody.conflicts.where((value) => value.path == path).firstOrNull;
  void _addLoaded(workspace.OpenedWorkspaceFile source) =>
      _active = _io!.addLoaded(_open, source);
  void _reset() {
    _custody.disposeFiles(_open);
    _custody.clear();
    _preRun.clear();
    _diffs = const [];
    _status = null;
    _presentationFailure = null;
    _io = null;
    _phase = CodeSessionPhase.closed;
  }

  @override
  void dispose() {
    _custody.disposeFiles(_open);
    super.dispose();
  }
}

WorkspaceWriteResult _defaultWrite(String root, String path, String disk,
        String buffer, List<int> bytes) =>
    const WorkspaceFileTransaction().compareAndWrite(
        canonicalRoot: root,
        requestedPath: path,
        expectedDiskSha256: disk,
        bufferSha256: buffer,
        bytes: bytes);
