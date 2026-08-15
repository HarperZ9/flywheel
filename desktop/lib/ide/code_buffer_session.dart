import 'dart:io';

import 'package:flutter/foundation.dart';

import '../services/code_draft_store.dart';
import 'diff.dart';
import 'workspace.dart' as workspace;

typedef OpenFile = workspace.OpenFile;
typedef CodeRecoveryKind = workspace.CodeRecoveryKind;
typedef CodeRecoveryConflict = workspace.CodeRecoveryConflict;
typedef CodeSessionFailure = workspace.CodeSessionFailure;
typedef CodeSessionException = workspace.CodeSessionException;

typedef CodeLoadFile = workspace.LoadedFile Function(String path);
typedef CodeSaveFile = workspace.SavedFile Function(String path, String text);

final class CodeBufferSession extends ChangeNotifier {
  CodeBufferSession({
    required this.draftStore,
    CodeLoadFile? loadFile,
    CodeSaveFile? saveFile,
    DateTime Function()? now,
  })  : _load = loadFile ?? workspace.loadFile,
        _save = saveFile ?? workspace.saveFile,
        _now = now ?? (() => DateTime.now().toUtc());

  final CodeDraftStore draftStore;
  final CodeLoadFile _load;
  final CodeSaveFile _save;
  final DateTime Function() _now;
  final List<OpenFile> _open = [];
  final List<CodeRecoveryConflict> _conflicts = [];
  final Map<String, String> _preRun = {};
  List<FileDiff> _diffs = const [];
  workspace.WorkspaceSessionIo? _io;
  int _active = -1;
  CodeSessionFailure? _failure;
  String? _status;

  String? get workspaceRoot => _io?.root;
  int get activeIndex => _active;
  List<OpenFile> get openFiles => List.unmodifiable(_open);
  List<CodeRecoveryConflict> get conflicts => List.unmodifiable(_conflicts);
  List<FileDiff> get diffs => List.unmodifiable(_diffs);
  CodeSessionFailure? get failure => _failure;
  String? get status => _status;
  List<CodeDraft> get drafts =>
      _io == null ? const [] : draftStore.load(workspaceRef: _io!.workspaceRef);
  List<String> get dirtyPaths => _io?.dirtyPaths(_open) ?? const [];

  void openWorkspace(String root) {
    try {
      _disposeFiles();
      _io = workspace.WorkspaceSessionIo.open(root);
      _failure = null;
      _status = null;
      _conflicts.clear();
      notifyListeners();
    } catch (_) {
      throw const CodeSessionException(CodeSessionFailure.invalidPath);
    }
  }

  void openFile(String absolutePath) {
    final opened = _openSource(absolutePath);
    _addLoaded(opened);
    notifyListeners();
  }

  void selectIndex(int index) {
    if (index < 0 || index >= _open.length) return;
    _active = index;
    notifyListeners();
  }

  void snapshot(String absolutePath) {
    final file = _find(absolutePath);
    if (file.readOnly) return;
    final bufferSha = workspace.codeTextSha256(file.controller.text);
    file.dirty = bufferSha != file.diskSha256;
    try {
      if (!file.dirty) {
        final current =
            drafts.where((draft) => draft.path == file.relativePath);
        if (current.isNotEmpty) {
          draftStore.delete(
              workspaceRef: _io!.workspaceRef,
              path: file.relativePath,
              expectedBufferSha256: current.single.bufferSha256);
        }
      } else {
        draftStore.save(
            workspaceRef: _io!.workspaceRef,
            draft: CodeDraft(
                path: file.relativePath,
                diskSha256: file.diskSha256,
                bufferSha256: bufferSha,
                text: file.controller.text,
                updatedAt: _now().toUtc()));
      }
      _setState(file, file.dirty, null, file.dirty ? 'draft saved' : null);
    } catch (_) {
      _setState(file, true, CodeSessionFailure.localStore, 'draft save failed');
    }
  }

  List<CodeRecoveryConflict> recover() {
    if (_io == null) {
      throw const CodeSessionException(CodeSessionFailure.invalidPath);
    }
    _conflicts.clear();
    for (final draft in drafts) {
      final view = _io!.inspect(draft);
      final disk = view.disk;
      if (view.state == workspace.DraftDiskState.missing) {
        _addLoaded(_io!.missing(view.path, draft),
            text: draft.text, dirty: true, readOnly: true);
        _outcome(CodeRecoveryKind.fileMissing, draft);
      } else if (view.state == workspace.DraftDiskState.buffer) {
        draftStore.delete(
            workspaceRef: _io!.workspaceRef,
            path: draft.path,
            expectedBufferSha256: draft.bufferSha256);
        _addLoaded(_io!.source(view.path, disk!));
        _outcome(CodeRecoveryKind.alreadySaved, draft,
            diskText: disk.content, diskSha: disk.sha256);
      } else if (view.state == workspace.DraftDiskState.baseline) {
        _addLoaded(_io!.source(view.path, disk!),
            text: draft.text, dirty: true);
        _outcome(CodeRecoveryKind.restored, draft,
            diskText: disk.content, diskSha: disk.sha256);
      } else {
        _addLoaded(_io!.source(view.path, disk!), dirty: true, readOnly: true);
        _outcome(CodeRecoveryKind.diskChanged, draft,
            diskText: disk.content, diskSha: disk.sha256);
      }
    }
    notifyListeners();
    return List.unmodifiable(_conflicts);
  }

  bool save(String absolutePath) {
    final file = _find(absolutePath);
    if (!file.dirty || file.readOnly || _failure != null) return !file.dirty;
    final current = _diskForSave(file);
    if (current == null) return false;
    final bufferSha = workspace.codeTextSha256(file.controller.text);
    try {
      final saved = _save(file.path, file.controller.text);
      if (saved.sha256 != bufferSha) throw StateError('readback');
      draftStore.delete(
          workspaceRef: _io!.workspaceRef,
          path: file.relativePath,
          expectedBufferSha256: bufferSha);
      file.diskSha256 = bufferSha;
      _removeConflict(file.relativePath);
      _setState(file, false, null, 'saved ${file.name}');
      return true;
    } catch (_) {
      _setState(file, true, CodeSessionFailure.writeFailed, 'save failed');
      return false;
    }
  }

  bool discard(String absolutePath) {
    final file = _find(absolutePath);
    if (!file.dirty) return true;
    try {
      final draft =
          drafts.singleWhere((item) => item.path == file.relativePath);
      draftStore.delete(
          workspaceRef: _io!.workspaceRef,
          path: file.relativePath,
          expectedBufferSha256: draft.bufferSha256);
      if (File(file.path).existsSync()) {
        final disk = _openSource(file.path).loaded;
        file.controller.text = disk.content;
        file.diskSha256 = disk.sha256;
        file.readOnly = disk.readOnly;
        file.note = disk.note;
      } else {
        file.controller.clear();
        file.readOnly = true;
        file.note = 'file missing';
      }
      _removeConflict(file.relativePath);
      _setState(file, false, null, 'discarded ${file.name}');
      return true;
    } catch (_) {
      _setState(file, true, CodeSessionFailure.localStore, 'discard failed');
      return false;
    }
  }

  bool closeFile(String absolutePath) {
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
    if (_open.any((file) => file.dirty)) return false;
    _disposeFiles();
    _io = null;
    _conflicts.clear();
    notifyListeners();
    return true;
  }

  void snapshotOpenFiles() => _io!.snapshot(_open, _preRun);

  void report(String? message) {
    _status = message;
    notifyListeners();
  }

  void reloadCleanFiles() {
    _diffs = _io!.reloadClean(_open, _preRun, _load);
    notifyListeners();
  }

  workspace.LoadedFile? _diskForSave(OpenFile file) {
    if (!File(file.path).existsSync()) {
      _conflictFor(file, CodeRecoveryKind.fileMissing);
      return null;
    }
    final current = _openSource(file.path).loaded;
    if (current.sha256 != file.diskSha256) {
      _conflictFor(file, CodeRecoveryKind.diskChanged, disk: current);
      return null;
    }
    return current;
  }

  void _conflictFor(OpenFile file, CodeRecoveryKind kind,
      {workspace.LoadedFile? disk}) {
    final draft = drafts.singleWhere((item) => item.path == file.relativePath);
    _removeConflict(file.relativePath);
    _outcome(kind, draft, diskText: disk?.content, diskSha: disk?.sha256);
    _failure = CodeSessionFailure.writeFailed;
    notifyListeners();
  }

  void _outcome(CodeRecoveryKind kind, CodeDraft draft,
      {String? diskText, String? diskSha}) {
    _conflicts
        .add(CodeRecoveryConflict(kind, draft.path, draft, diskText, diskSha));
  }

  void _addLoaded(workspace.OpenedWorkspaceFile source,
      {String? text, bool dirty = false, bool? readOnly}) {
    _active = _io!
        .addLoaded(_open, source, text: text, dirty: dirty, readOnly: readOnly);
  }

  workspace.OpenedWorkspaceFile _openSource(String path) {
    try {
      return _io!.openWith(path, _load);
    } catch (_) {
      throw const CodeSessionException(CodeSessionFailure.readFailed);
    }
  }

  OpenFile _find(String path) =>
      _open.firstWhere((file) => _io!.samePath(file.path, path),
          orElse: () =>
              throw const CodeSessionException(CodeSessionFailure.invalidPath));

  void _removeConflict(String path) =>
      _conflicts.removeWhere((conflict) => conflict.path == path);
  void _setState(
      OpenFile file, bool dirty, CodeSessionFailure? failure, String? status) {
    file.dirty = dirty;
    _failure = failure;
    _status = status;
    notifyListeners();
  }

  void _disposeFiles() {
    for (final file in _open) {
      file.controller.dispose();
    }
    _open.clear();
    _active = -1;
  }

  @override
  void dispose() {
    _disposeFiles();
    super.dispose();
  }
}
