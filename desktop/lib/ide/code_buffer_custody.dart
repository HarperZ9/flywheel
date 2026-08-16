import '../services/code_draft_store.dart';
import 'workspace.dart' as workspace;
import 'workspace_file_transaction.dart';

final class CodeRecoveryBatch {
  CodeRecoveryBatch(
      this.files, this.records, this.outcomes, this.conflicts, this.cleanup);
  final List<workspace.OpenFile> files;
  final List<StoredCodeDraft> records;
  final List<workspace.CodeRecoveryOutcome> outcomes;
  final List<workspace.CodeRecoveryConflict> conflicts;
  final List<StoredCodeDraft> cleanup;
}

final class CodeBufferCustody {
  CodeBufferCustody(this.store);
  final CodeDraftStore store;
  final List<StoredCodeDraft> records = [];
  final List<workspace.CodeRecoveryOutcome> outcomes = [];
  final List<workspace.CodeRecoveryConflict> conflicts = [];
  CodeRecoveryBatch? _pending;

  List<CodeDraft> get drafts =>
      List.unmodifiable(records.map((stored) => stored.draft));

  CodeRecoveryBatch recover(workspace.WorkspaceSessionIo io) {
    final pending = _pending;
    if (pending != null) {
      _cleanup(io, pending);
      return pending;
    }
    final loaded = store.load(workspaceRef: io.workspaceRef);
    final files = <workspace.OpenFile>[];
    final recovered = <workspace.CodeRecoveryOutcome>[];
    final blocked = <workspace.CodeRecoveryConflict>[];
    final retained = <StoredCodeDraft>[];
    final cleanup = <StoredCodeDraft>[];
    try {
      for (final stored in loaded) {
        final keep = _stage(io, stored, files, recovered, blocked);
        (keep ? retained : cleanup).add(stored);
      }
    } catch (_) {
      disposeFiles(files);
      rethrow;
    }
    final batch =
        CodeRecoveryBatch(files, retained, recovered, blocked, cleanup);
    try {
      _cleanup(io, batch);
      return batch;
    } catch (_) {
      _pending = batch;
      rethrow;
    }
  }

  void publish(CodeRecoveryBatch batch) {
    records
      ..clear()
      ..addAll(batch.records);
    outcomes
      ..clear()
      ..addAll(batch.outcomes);
    conflicts
      ..clear()
      ..addAll(batch.conflicts);
  }

  List<workspace.CodeRecoveryOutcome> recoverInto(
      workspace.WorkspaceSessionIo io, List<workspace.OpenFile> target) {
    final batch = recover(io);
    disposeFiles(target);
    target.addAll(batch.files);
    publish(batch);
    return List.unmodifiable(batch.outcomes);
  }

  StoredCodeDraft save(workspace.WorkspaceSessionIo io, workspace.OpenFile file,
      String digest, DateTime updatedAt) {
    final stored = store.save(
        workspaceRef: io.workspaceRef,
        draft: CodeDraft(
            path: file.relativePath,
            diskSha256: file.diskSha256,
            bufferSha256: digest,
            text: file.controller.text,
            updatedAt: updatedAt));
    replace(stored);
    return stored;
  }

  bool generationCurrent(
      workspace.WorkspaceSessionIo io, workspace.OpenFile file) {
    final loaded = store.load(workspaceRef: io.workspaceRef);
    final current =
        loaded.where((item) => item.draft.path == file.relativePath);
    if (current.length != 1 ||
        current.single.recordSha256 != file.journalRecordSha256) {
      return false;
    }
    replace(current.single);
    return true;
  }

  bool hasJournal(workspace.OpenFile file) =>
      file.journalBufferSha256 ==
          workspace.codeTextSha256(file.controller.text) &&
      file.journalRecordSha256 != null;
  bool closable(workspace.OpenFile file) =>
      file.journalFailure == null && hasJournal(file);

  bool delete(workspace.WorkspaceSessionIo io, workspace.OpenFile file,
      {bool allowAbsent = false}) {
    final stored = record(file.relativePath);
    if (stored == null) return allowAbsent;
    try {
      store.delete(
          workspaceRef: io.workspaceRef,
          path: file.relativePath,
          expectedBufferSha256: stored.draft.bufferSha256,
          expectedRecordSha256: stored.recordSha256);
      records.remove(stored);
      file
        ..journalBufferSha256 = null
        ..journalRecordSha256 = null
        ..journalFailure = null;
      return true;
    } catch (_) {
      file.journalFailure = workspace.CodeSessionFailure.localStore;
      return false;
    }
  }

  void addConflict(workspace.WorkspaceSessionIo io, workspace.OpenFile file,
      CodeDiskFailure failure) {
    final stored = record(file.relativePath);
    if (stored == null) return;
    final disk = failure == CodeDiskFailure.changed
        ? io.openFile(file.path).loaded
        : null;
    file.readOnly = true;
    removeConflict(file.relativePath);
    conflicts.add(workspace.CodeRecoveryConflict(
        failure == CodeDiskFailure.missing
            ? workspace.CodeRecoveryKind.fileMissing
            : workspace.CodeRecoveryKind.diskChanged,
        file.relativePath,
        stored,
        disk?.content,
        disk?.sha256));
  }

  StoredCodeDraft? record(String path) =>
      records.where((item) => item.draft.path == path).firstOrNull;
  void replace(StoredCodeDraft stored) {
    records.removeWhere((item) => item.draft.path == stored.draft.path);
    records.add(stored);
  }

  void removeConflict(String path) =>
      conflicts.removeWhere((value) => value.path == path);
  void clear() {
    disposePending();
    records.clear();
    outcomes.clear();
    conflicts.clear();
  }

  void disposePending() {
    final pending = _pending;
    if (pending != null) disposeFiles(pending.files);
    _pending = null;
  }

  void disposeFiles(List<workspace.OpenFile> files) {
    for (final file in files) {
      file.controller.dispose();
    }
    files.clear();
  }

  void _cleanup(workspace.WorkspaceSessionIo io, CodeRecoveryBatch batch) {
    while (batch.cleanup.isNotEmpty) {
      final stored = batch.cleanup.first;
      store.delete(
          workspaceRef: io.workspaceRef,
          path: stored.draft.path,
          expectedBufferSha256: stored.draft.bufferSha256,
          expectedRecordSha256: stored.recordSha256);
      batch.cleanup.removeAt(0);
    }
    _pending = null;
  }

  bool _stage(
      workspace.WorkspaceSessionIo io,
      StoredCodeDraft stored,
      List<workspace.OpenFile> files,
      List<workspace.CodeRecoveryOutcome> recovered,
      List<workspace.CodeRecoveryConflict> blocked) {
    final draft = stored.draft;
    final view = io.inspect(draft);
    final disk = view.disk;
    final kind = switch (view.state) {
      workspace.DraftDiskState.missing =>
        workspace.CodeRecoveryKind.fileMissing,
      workspace.DraftDiskState.buffer =>
        workspace.CodeRecoveryKind.alreadySaved,
      workspace.DraftDiskState.baseline => workspace.CodeRecoveryKind.restored,
      workspace.DraftDiskState.changed =>
        workspace.CodeRecoveryKind.diskChanged,
    };
    recovered.add(workspace.CodeRecoveryOutcome(kind, draft.path));
    if (kind == workspace.CodeRecoveryKind.alreadySaved) {
      io.addLoaded(files, io.source(view.path, disk!));
      return false;
    }
    final source = kind == workspace.CodeRecoveryKind.fileMissing
        ? io.missing(view.path, draft)
        : io.source(view.path, disk!);
    io.addLoaded(files, source,
        text: draft.text,
        dirty: true,
        readOnly: kind != workspace.CodeRecoveryKind.restored);
    files.last
      ..journalBufferSha256 = draft.bufferSha256
      ..journalRecordSha256 = stored.recordSha256;
    if (kind == workspace.CodeRecoveryKind.diskChanged ||
        kind == workspace.CodeRecoveryKind.fileMissing) {
      blocked.add(workspace.CodeRecoveryConflict(
          kind, draft.path, stored, disk?.content, disk?.sha256));
    }
    return true;
  }
}
