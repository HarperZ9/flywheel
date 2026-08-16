import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/ide/code_buffer_session.dart';
import 'package:flywheel_desktop/ide/workspace_file_transaction.dart';
import 'package:flywheel_desktop/services/code_draft_store.dart';

const _workspace =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _disk =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
final _updated = DateTime.parse('2026-08-15T12:00:00.000Z');

Directory _temp(String name) {
  final value = Directory.systemTemp.createTempSync(name);
  addTearDown(
      () => value.existsSync() ? value.deleteSync(recursive: true) : null);
  return value;
}

CodeDraft _draft(String text, {String path = 'lib/main.dart'}) => CodeDraft(
    path: path,
    diskSha256: _disk,
    bufferSha256: sha256.convert(utf8.encode(text)).toString(),
    text: text,
    updatedAt: _updated);

File _record(Directory root, [String path = 'lib/main.dart']) =>
    File('${root.path}/$_workspace/${sha256.convert(utf8.encode(path))}.json');

File _owned(File record, String kind, String recordSha, [String? nonce]) =>
    File('${record.path}.fw-$kind.$pid.${nonce ?? 'a' * 32}.$recordSha.tmp');

void main() {
  _startupTests();
  _startupFailureTests();
  _generationTests();
  _junctionTests();
  _platformTests();
}

void _startupTests() {
  test('valid target wins over an abandoned owned write', () {
    final root = _temp('code-startup-prior-');
    final store = CodeDraftStore(root: root);
    final stored = store.save(workspaceRef: _workspace, draft: _draft('prior'));
    final target = _record(root);
    final orphan = _owned(target, 'write', stored.recordSha256)
      ..writeAsBytesSync(target.readAsBytesSync(), flush: true);
    final loaded = store.load(workspaceRef: _workspace);
    expect(loaded.single.recordSha256, stored.recordSha256);
    expect(loaded.single.draft.text, 'prior');
    expect(orphan.existsSync(), isFalse);
    expect(target.existsSync(), isTrue);
  });
  test('complete first write promotes while partial bytes quarantine', () {
    final sourceRoot = _temp('code-startup-source-');
    final source = CodeDraftStore(root: sourceRoot)
        .save(workspaceRef: _workspace, draft: _draft('complete'));
    final bytes = _record(sourceRoot).readAsBytesSync();
    final completeRoot = _temp('code-startup-complete-');
    final completeTarget = _record(completeRoot)
      ..parent.createSync(recursive: true);
    _owned(completeTarget, 'write', source.recordSha256)
        .writeAsBytesSync(bytes, flush: true);
    expect(
        CodeDraftStore(root: completeRoot)
            .load(workspaceRef: _workspace)
            .single
            .draft
            .text,
        'complete');
    expect(completeTarget.existsSync(), isTrue);

    final partialRoot = _temp('code-startup-partial-');
    final partialTarget = _record(partialRoot)
      ..parent.createSync(recursive: true);
    final partial = utf8.encode('{');
    final partialSha = sha256.convert(partial).toString();
    final orphan = _owned(partialTarget, 'write', partialSha)
      ..writeAsBytesSync(partial, flush: true);
    expect(CodeDraftStore(root: partialRoot).load(workspaceRef: _workspace),
        isEmpty);
    expect(orphan.existsSync(), isFalse);
    expect(partialTarget.existsSync(), isFalse);
  });
}

void _startupFailureTests() {
  test('unexpected entries fail before any scavenging mutation', () {
    final root = _temp('code-startup-foreign-');
    final store = CodeDraftStore(root: root);
    final stored = store.save(workspaceRef: _workspace, draft: _draft('prior'));
    final target = _record(root);
    final orphan = _owned(target, 'write', stored.recordSha256)
      ..writeAsBytesSync(target.readAsBytesSync());
    final foreign = File('${target.parent.path}/foreign.tmp')
      ..writeAsStringSync('x');
    final before = target.readAsBytesSync();
    expect(() => store.load(workspaceRef: _workspace),
        throwsA(isA<CodeDraftStoreException>()));
    expect(target.readAsBytesSync(), before);
    expect(orphan.existsSync(), isTrue);
    expect(foreign.readAsStringSync(), 'x');
  });
  test('conflicting complete generations block startup', () {
    final aRoot = _temp('code-startup-a-');
    final bRoot = _temp('code-startup-b-');
    final a = CodeDraftStore(root: aRoot)
        .save(workspaceRef: _workspace, draft: _draft('a'));
    final b = CodeDraftStore(root: bRoot)
        .save(workspaceRef: _workspace, draft: _draft('b'));
    final root = _temp('code-startup-conflict-');
    final target = _record(root)..parent.createSync(recursive: true);
    _owned(target, 'write', a.recordSha256, 'a' * 32)
        .writeAsBytesSync(_record(aRoot).readAsBytesSync());
    _owned(target, 'write', b.recordSha256, 'b' * 32)
        .writeAsBytesSync(_record(bRoot).readAsBytesSync());
    expect(() => CodeDraftStore(root: root).load(workspaceRef: _workspace),
        throwsA(isA<CodeDraftStoreException>()));
    expect(target.existsSync(), isFalse);
  });
  test('owned complete bytes cannot promote under another path hash', () {
    final sourceRoot = _temp('code-startup-path-source-');
    final stored = CodeDraftStore(root: sourceRoot)
        .save(workspaceRef: _workspace, draft: _draft('a'));
    final root = _temp('code-startup-path-mismatch-');
    final wrongTarget = _record(root, 'lib/other.dart')
      ..parent.createSync(recursive: true);
    final orphan = _owned(wrongTarget, 'write', stored.recordSha256);
    orphan.writeAsBytesSync(_record(sourceRoot).readAsBytesSync());
    expect(() => CodeDraftStore(root: root).load(workspaceRef: _workspace),
        throwsA(isA<CodeDraftStoreException>()));
    expect(wrongTarget.existsSync(), isFalse);
    expect(orphan.existsSync(), isTrue);
  });
}

void _generationTests() {
  test('delete tombstone restarts and stale token cannot delete newer data',
      () {
    final root = _temp('code-delete-generation-');
    final store = CodeDraftStore(root: root);
    final first = store.save(workspaceRef: _workspace, draft: _draft('first'));
    final target = _record(root);
    target.renameSync(_owned(target, 'delete', first.recordSha256).path);
    expect(store.load(workspaceRef: _workspace).single.draft.text, 'first');
    final newer = store.save(workspaceRef: _workspace, draft: _draft('newer'));
    expect(
        () => store.delete(
            workspaceRef: _workspace,
            path: first.draft.path,
            expectedBufferSha256: first.draft.bufferSha256,
            expectedRecordSha256: first.recordSha256),
        throwsA(isA<CodeDraftStoreException>()));
    expect(store.load(workspaceRef: _workspace).single.recordSha256,
        newer.recordSha256);
  });

  test('a second store observes the active per-record lock', () {
    final root = _temp('code-record-lock-');
    CodeDraftStoreException? contention;
    late CodeDraftStore second;
    final first = CodeDraftStore(
        root: root,
        beforeRename: (_) {
          try {
            second.save(workspaceRef: _workspace, draft: _draft('second'));
          } on CodeDraftStoreException catch (error) {
            contention = error;
          }
        });
    second = CodeDraftStore(root: root);
    first.save(workspaceRef: _workspace, draft: _draft('first'));
    expect(contention?.failure, CodeDraftFailure.storeBusy);
    expect(first.load(workspaceRef: _workspace).single.draft.text, 'first');
  });

  test('failed older save never restores over an unknown newer generation', () {
    final root = _temp('code-save-generation-');
    final store = CodeDraftStore(root: root);
    store.save(workspaceRef: _workspace, draft: _draft('prior'));
    final otherRoot = _temp('code-save-newer-');
    CodeDraftStore(root: otherRoot)
        .save(workspaceRef: _workspace, draft: _draft('newer'));
    final newerBytes = _record(otherRoot).readAsBytesSync();
    final failing = CodeDraftStore(
        root: root,
        renameFile: (temporary, target) {
          temporary.renameSync(target);
          File(target).writeAsBytesSync(newerBytes, flush: true);
          throw StateError('injected');
        });
    expect(() => failing.save(workspaceRef: _workspace, draft: _draft('older')),
        throwsA(isA<CodeDraftStoreException>()));
    expect(store.load(workspaceRef: _workspace).single.draft.text, 'newer');
  });
}

bool _junction(Directory link, Directory target) {
  if (!Platform.isWindows) {
    markTestSkipped('Windows junction case');
    return false;
  }
  final result =
      Process.runSync('cmd', ['/c', 'mklink', '/J', link.path, target.path]);
  if (result.exitCode != 0) {
    markTestSkipped('Windows junction creation unavailable');
    return false;
  }
  return true;
}

void _junctionTests() {
  test('real junction custody root refuses outside writes', () {
    final parent = _temp('code-junction-custody-');
    final outside = Directory('${parent.path}/outside')..createSync();
    final link = Directory('${parent.path}/drafts');
    if (!_junction(link, outside)) return;
    expect(
        () => CodeDraftStore(root: link)
            .save(workspaceRef: _workspace, draft: _draft('x')),
        throwsA(isA<CodeDraftStoreException>()));
    expect(outside.listSync(), isEmpty);
  });

  test('real junction target is outside the workspace handle boundary', () {
    final root = _temp('code-junction-workspace-');
    final outside = _temp('code-junction-outside-');
    final target = File('${outside.path}/target.dart')..writeAsStringSync('x');
    final link = Directory('${root.path}/linked');
    if (!_junction(link, outside)) return;
    final transaction = WorkspaceFileTransaction();
    expect(
        () => transaction.read(
            canonicalRoot: root.resolveSymbolicLinksSync(),
            requestedPath: '${link.path}/target.dart'),
        throwsA(isA<WorkspaceFileException>()));
    expect(target.readAsStringSync(), 'x');
  });
}

void _platformTests() {
  test('Windows casing deduplicates while dot and space aliases refuse', () {
    if (!Platform.isWindows) {
      markTestSkipped('Windows path alias case');
      return;
    }
    final root = _temp('code-windows-alias-');
    final file = File('${root.path}/Case.dart')..writeAsStringSync('x');
    final session = CodeBufferSession(
        draftStore: CodeDraftStore(root: _temp('code-windows-drafts-')))
      ..openWorkspace(root.path)
      ..recover()
      ..openFile(file.path)
      ..openFile(file.path.toUpperCase());
    expect(session.openFiles, hasLength(1));
    for (final suffix in ['.', ' ']) {
      expect(
          () => WorkspaceFileTransaction().read(
              canonicalRoot: root.resolveSymbolicLinksSync(),
              requestedPath: '${file.path}$suffix'),
          throwsA(isA<WorkspaceFileException>()));
    }
    expect(
        () => WorkspaceFileTransaction().read(
            canonicalRoot: root.resolveSymbolicLinksSync(),
            requestedPath: 'FILE:${file.path}'),
        throwsA(isA<WorkspaceFileException>()));
  });
  test('replacement after handle validation cannot write through junction', () {
    final root = _temp('code-junction-race-');
    final outside = _temp('code-junction-race-outside-');
    final inside = Directory('${root.path}/inside')..createSync();
    final original = File('${inside.path}/target.dart')
      ..writeAsStringSync('old');
    final escaped = File('${outside.path}/target.dart')
      ..writeAsStringSync('outside');
    if (!Platform.isWindows) {
      markTestSkipped('Windows handle replacement case');
      return;
    }
    final transaction = WorkspaceFileTransaction(afterHandleValidated: () {
      inside.renameSync('${root.path}/held');
      _junction(Directory(inside.path), outside);
    });
    final bytes = utf8.encode('new');
    expect(
        () => transaction.compareAndWrite(
            canonicalRoot: root.resolveSymbolicLinksSync(),
            requestedPath: original.path,
            expectedDiskSha256: sha256.convert(utf8.encode('old')).toString(),
            bufferSha256: sha256.convert(bytes).toString(),
            bytes: bytes),
        throwsA(isA<WorkspaceFileException>()));
    expect(escaped.readAsStringSync(), 'outside');
  });
}
