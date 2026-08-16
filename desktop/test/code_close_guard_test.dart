import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/ide/code_buffer_session.dart';
import 'package:flywheel_desktop/ide/unsaved_work_guard.dart';
import 'package:flywheel_desktop/ide/workspace.dart' as workspace;
import 'package:flywheel_desktop/ide/workspace_file_transaction.dart';
import 'package:flywheel_desktop/services/code_draft_store.dart';

Directory _temp(String name) {
  final value = Directory.systemTemp.createTempSync(name);
  addTearDown(() => value.deleteSync(recursive: true));
  return value;
}

class SessionHarness {
  SessionHarness(
      {CodeDraftStore? store, CodeCompareAndWrite? compareAndWrite}) {
    root = _temp('code-session-');
    draftRoot = _temp('code-session-drafts-');
    file = File('${root.path}/lib/main.dart')
      ..parent.createSync(recursive: true)
      ..writeAsStringSync('baseline');
    session = CodeBufferSession(
        draftStore: store ?? CodeDraftStore(root: draftRoot),
        compareAndWrite: compareAndWrite);
    session.openWorkspace(root.path);
    session.recover();
    session.openFile(file.path);
  }
  late final Directory root, draftRoot;
  late final File file;
  late final CodeBufferSession session;
  OpenFile get active => session.openFiles[session.activeIndex];
  CodeBufferSession restart() =>
      CodeBufferSession(draftStore: CodeDraftStore(root: draftRoot))
        ..openWorkspace(root.path);
  void edit(String text) =>
      session.snapshot((active..controller.text = text).path);
}

void main() {
  _snapshotRecoveryTests();
  _conflictTests();
  _guardTests();
  _failureTests();
  _journalGenerationTests();
}

void _snapshotRecoveryTests() {
  test('edit snapshots before return and same baseline restores dirty text',
      () {
    final first = SessionHarness();
    first.edit('edited λ 100%');
    expect(first.active.dirty, isTrue);
    expect(first.session.dirtyPaths, ['lib/main.dart']);
    expect(first.session.drafts, hasLength(1));
    first.session.dispose();
    final second = first.restart();
    final outcomes = second.recover();
    expect(outcomes.single.kind, CodeRecoveryKind.restored);
    expect(second.openFiles.single.controller.text, 'edited λ 100%');
    expect(second.openFiles.single.dirty, isTrue);
  });

  test('disk equal to buffer cleans interrupted save and opens clean', () {
    final first = SessionHarness()..edit('landed');
    first.file.writeAsStringSync('landed', flush: true);
    first.session.dispose();
    final second = first.restart();
    expect(second.recover().single.kind, CodeRecoveryKind.alreadySaved);
    expect(second.openFiles.single.controller.text, 'landed');
    expect(second.openFiles.single.dirty, isFalse);
    expect(second.drafts, isEmpty);
  });
}

void _conflictTests() {
  test('changed and missing disk retain journal with read-only comparison',
      () async {
    final changed = SessionHarness()..edit('draft text');
    changed.file.writeAsStringSync('external text');
    changed.session.dispose();
    final restored = changed.restart();
    restored.recover();
    final conflict = restored.conflicts.single;
    expect([conflict.kind, conflict.diskText, conflict.stored.draft.text],
        [CodeRecoveryKind.diskChanged, 'external text', 'draft text']);
    expect(restored.dirtyPaths, ['lib/main.dart']);
    expect(restored.drafts, hasLength(1));
    expect(changed.file.readAsStringSync(), 'external text');
    changed.file.deleteSync();
    final missing = changed.restart();
    expect(missing.recover().single.kind, CodeRecoveryKind.fileMissing);
    expect(changed.file.existsSync(), isFalse);
    expect(missing.drafts, hasLength(1));
    expect(missing.dirtyPaths, ['lib/main.dart']);
    final guard = UnsavedWorkGuard(
        session: missing, prompt: (_) async => CloseChoice.discard);
    expect(await guard.requestApplicationExit(), isTrue);
    expect(missing.drafts, isEmpty);
  });

  test('save compares captured disk digest and writes nothing after drift', () {
    final harness = SessionHarness()..edit('draft');
    harness.file.writeAsStringSync('external');
    expect(harness.session.save(harness.file.path), isFalse);
    expect(harness.file.readAsStringSync(), 'external');
    expect(harness.active.dirty, isTrue);
    expect(harness.session.conflicts.single.kind, CodeRecoveryKind.diskChanged);
  });
}

void _guardTests() {
  test('file and workspace Save Discard Cancel use stable relative paths',
      () async {
    final harness = SessionHarness()..edit('one');
    final choices = [CloseChoice.cancel, CloseChoice.save, CloseChoice.discard];
    final requests = <UnsavedWorkRequest>[];
    final guard = UnsavedWorkGuard(
        session: harness.session,
        prompt: (request) async {
          requests.add(request);
          return choices.removeAt(0);
        });
    expect(await guard.requestFileClose(harness.file.path), isFalse);
    expect(harness.active.dirty, isTrue);
    expect(requests.single.paths, ['lib/main.dart']);
    expect(await guard.requestNavigation('Chat'), isTrue);
    expect(harness.file.readAsStringSync(), 'one');
    expect(harness.active.dirty, isFalse);
    harness.edit('two');
    final other = File('${harness.root.path}/lib/other.dart')
      ..writeAsStringSync('other baseline');
    harness.session.openFile(other.path);
    harness.edit('other dirty');
    expect(harness.session.dirtyPaths, ['lib/main.dart', 'lib/other.dart']);
    expect(await guard.requestWorkspaceClose(), isTrue);
    expect(harness.session.workspaceRoot, isNull);
    expect([harness.file.readAsStringSync(), other.readAsStringSync()],
        ['one', 'other baseline']);
  });

  test('one prompt is in flight and a concurrent request fails closed',
      () async {
    final harness = SessionHarness()..edit('pending');
    final completer = Completer<CloseChoice>();
    var prompts = 0;
    final guard = UnsavedWorkGuard(
        session: harness.session,
        prompt: (_) {
          prompts++;
          return completer.future;
        });
    final first = guard.requestNavigation('Chat');
    expect(await guard.requestApplicationExit(), isFalse);
    expect(prompts, 1);
    harness.edit('changed while prompt was open');
    completer.complete(CloseChoice.discard);
    expect(await first, isFalse);
    expect(harness.active.controller.text, 'changed while prompt was open');
  });

  test('file prompt keeps stable path when active tab changes', () async {
    final harness = SessionHarness()..edit('first dirty');
    final second = File('${harness.root.path}/lib/other.dart')
      ..writeAsStringSync('second');
    harness.session.openFile(second.path);
    final pending = Completer<CloseChoice>();
    final close = UnsavedWorkGuard(
        session: harness.session, prompt: (_) => pending.future);
    final result = close.requestFileClose(harness.file.path);
    harness.session.selectIndex(1);
    pending.complete(CloseChoice.discard);
    expect(await result, isTrue);
    expect(harness.session.openFiles.single.path,
        second.resolveSymbolicLinksSync());
    expect(harness.session.activeIndex, 0);
  });
}

void _failureTests() {
  test('journal write or delete failure remains dirty and blocks closure',
      () async {
    final root = _temp('code-failure-store-');
    var failWrite = false;
    var failDelete = false;
    final store = CodeDraftStore(
        root: root,
        beforeRename: (_) => failWrite ? throw StateError('injected') : null,
        deleteFile: (file) =>
            failDelete ? throw StateError('injected') : file.deleteSync());
    final harness = SessionHarness(store: store)..edit('first');
    failWrite = true;
    harness.edit('second');
    expect(harness.session.failure, isNotNull);
    failWrite = false;
    harness.edit('second');
    failDelete = true;
    final guard = UnsavedWorkGuard(
        session: harness.session, prompt: (_) async => CloseChoice.discard);
    expect(await guard.requestApplicationExit(), isFalse);
    expect(harness.active.dirty, isTrue);
    expect(harness.session.drafts, hasLength(1));
    harness.edit('baseline');
    expect(harness.active.dirty, isTrue);
    expect(harness.session.closeAdmissionReady, isFalse);
    expect(harness.session.drafts, hasLength(1));
  });

  test('disk failure is per-buffer and retries with the same journal', () {
    var calls = 0;
    final harness = SessionHarness(compareAndWrite:
        (root, requestedPath, expectedDiskSha256, bufferSha256, bytes) {
      calls++;
      if (calls == 1) {
        throw const WorkspaceFileException(CodeDiskFailure.writeFailed);
      }
      File(requestedPath).writeAsBytesSync(bytes, flush: true);
      return WorkspaceWriteResult(
          WorkspaceWriteDisposition.saved, requestedPath, bufferSha256);
    })
      ..edit('changed');
    expect(harness.session.save(harness.file.path), isFalse);
    expect(harness.active.diskFailure, CodeDiskFailure.writeFailed);
    expect(harness.active.journalRecordSha256, isNotNull);
    expect(harness.session.save(harness.file.path), isTrue);
    expect(calls, 2);
    expect(harness.active.dirty, isFalse);
  });

  test('successful B cannot clear A journal failure or authorize A disk', () {
    var failJournal = false;
    final store = CodeDraftStore(
        root: _temp('code-buffer-isolation-'),
        beforeRename: (_) => failJournal ? throw StateError('injected') : null);
    final harness = SessionHarness(store: store)..edit('a-one');
    failJournal = true;
    harness.edit('a-two');
    final a = harness.active;
    failJournal = false;
    final bFile = File('${harness.root.path}/lib/b.dart')
      ..writeAsStringSync('b-base');
    harness.session.openFile(bFile.path);
    harness.edit('b-one');
    expect(a.journalFailure, isNotNull);
    expect(harness.active.journalFailure, isNull);
    expect(harness.session.closeAdmissionReady, isFalse);
    expect(harness.session.save(a.path), isFalse);
    expect(harness.file.readAsStringSync(), 'baseline');
  });
}

void _journalGenerationTests() {
  test('stale journal generation blocks the disk write', () {
    final harness = SessionHarness()..edit('mine');
    final oldDisk = harness.file.readAsStringSync();
    final text = 'other journal';
    CodeDraftStore(root: harness.draftRoot).save(
        workspaceRef: workspace
            .workspaceReference(harness.root.resolveSymbolicLinksSync()),
        draft: CodeDraft(
            path: 'lib/main.dart',
            diskSha256: sha256.convert(utf8.encode(oldDisk)).toString(),
            bufferSha256: sha256.convert(utf8.encode(text)).toString(),
            text: text,
            updatedAt: DateTime.parse('2026-08-15T12:00:00Z')));
    expect(harness.session.save(harness.file.path), isFalse);
    expect(harness.session.phase, CodeSessionPhase.recoveryBlocked);
    expect(harness.file.readAsStringSync(), oldDisk);
  });

  test('already-written disk retries exact journal cleanup', () {
    var failDelete = true;
    final root = _temp('code-cleanup-retry-');
    final store = CodeDraftStore(
        root: root,
        deleteFile: (file) {
          if (failDelete) throw StateError('injected');
          file.deleteSync();
        });
    final harness = SessionHarness(store: store)..edit('landed');
    harness.file.writeAsStringSync('landed', flush: true);
    expect(harness.session.save(harness.file.path), isFalse);
    expect(harness.active.journalRecordSha256, isNotNull);
    expect(harness.session.closeAdmissionReady, isFalse);
    failDelete = false;
    expect(harness.session.save(harness.file.path), isTrue);
    expect(harness.active.dirty, isFalse);
    expect(harness.session.drafts, isEmpty);
  });
}
