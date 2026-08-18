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
void _fails<T>(void Function() action, [Matcher? matcher]) =>
    expect(action, throwsA(matcher ?? isA<T>()));

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
    _fails<CodeDraftStoreException>(() => store.load(workspaceRef: _workspace));
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
    _fails<CodeDraftStoreException>(
        () => CodeDraftStore(root: root).load(workspaceRef: _workspace));
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
    _fails<CodeDraftStoreException>(
        () => CodeDraftStore(root: root).load(workspaceRef: _workspace));
    expect(wrongTarget.existsSync(), isFalse);
    expect(orphan.existsSync(), isTrue);
  });
}

void _generationTests() {
  test('delete restart and stale token cannot delete newer data', () {
    final root = _temp('code-delete-generation-');
    final store = CodeDraftStore(root: root);
    final first = store.save(workspaceRef: _workspace, draft: _draft('first'));
    final target = _record(root);
    target.renameSync(_owned(target, 'delete', first.recordSha256).path);
    expect(store.load(workspaceRef: _workspace).single.draft.text, 'first');
    final newer = store.save(workspaceRef: _workspace, draft: _draft('newer'));
    _fails<CodeDraftStoreException>(() => store.delete(
        workspaceRef: _workspace,
        path: first.draft.path,
        expectedBufferSha256: first.draft.bufferSha256,
        expectedRecordSha256: first.recordSha256));
    expect(store.load(workspaceRef: _workspace).single.recordSha256,
        newer.recordSha256);
  });

  test('failed older save never restores over an unknown newer generation', () {
    final root = _temp('code-save-generation-');
    final store = CodeDraftStore(root: root);
    store.save(workspaceRef: _workspace, draft: _draft('prior'));
    if (!Platform.isWindows) {
      final target = _record(root), before = target.readAsBytesSync();
      final outside = File('${_temp('code-rollback-outside-').path}/outside')
        ..writeAsStringSync('outside');
      var rollbackReady = false, swapped = false;
      final racing = CodeDraftStore(
          root: root,
          renameFile: (temporary, path) {
            temporary.renameSync(path);
            File(path).writeAsStringSync('{}');
            rollbackReady = true;
            throw StateError('injected');
          },
          readFile: (file) {
            final bytes = file.readAsBytesSync();
            if (rollbackReady && file.path == target.path) {
              file.deleteSync();
              Link(file.path).createSync(outside.path);
              swapped = true;
            }
            return bytes;
          });
      _fails<CodeDraftStoreException>(
          () => racing.save(workspaceRef: _workspace, draft: _draft('next')));
      expect(swapped && outside.readAsStringSync() == 'outside', isTrue);
      expect(target.readAsBytesSync(), before);
      expect(Link(target.path).existsSync(), isFalse);
    }
    final other = CodeDraftStore(root: _temp('code-save-newer-'));
    other.save(workspaceRef: _workspace, draft: _draft('newer'));
    final newerBytes = _record(other.storageRoot).readAsBytesSync();
    final failing = CodeDraftStore(
        root: root,
        renameFile: (temporary, target) {
          temporary.renameSync(target);
          File(target).writeAsBytesSync(newerBytes, flush: true);
          throw StateError('injected');
        });
    _fails<CodeDraftStoreException>(
        () => failing.save(workspaceRef: _workspace, draft: _draft('older')));
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
    _fails<CodeDraftStoreException>(() => CodeDraftStore(root: link)
        .save(workspaceRef: _workspace, draft: _draft('x')));
    expect(outside.listSync(), isEmpty);
  });

  test('real junction target is outside the workspace handle boundary', () {
    final root = _temp('code-junction-workspace-');
    final outside = _temp('code-junction-outside-');
    final target = File('${outside.path}/target.dart')..writeAsStringSync('x');
    final link = Directory('${root.path}/linked');
    if (!_junction(link, outside)) return;
    final transaction = WorkspaceFileTransaction();
    _fails<WorkspaceFileException>(() => transaction.read(
        canonicalRoot: root.resolveSymbolicLinksSync(),
        requestedPath: '${link.path}/target.dart'));
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
      _fails<WorkspaceFileException>(() => WorkspaceFileTransaction().read(
          canonicalRoot: root.resolveSymbolicLinksSync(),
          requestedPath: '${file.path}$suffix'));
    }
    _fails<WorkspaceFileException>(() => WorkspaceFileTransaction().read(
        canonicalRoot: root.resolveSymbolicLinksSync(),
        requestedPath: 'FILE:${file.path}'));
  });
  test('replacement after handle validation cannot write through junction', () {
    final root = _temp('code-junction-race-');
    final outside = _temp('code-junction-race-outside-');
    final inside = Directory('${root.path}/inside')..createSync();
    final original = File('${inside.path}/target.dart')
      ..writeAsStringSync('old');
    final escaped = File('${outside.path}/target.dart')
      ..writeAsStringSync('outside');
    final transaction = WorkspaceFileTransaction(afterHandleValidated: () {
      inside.renameSync('${root.path}/held');
      _junction(Directory(inside.path), outside);
    });
    final bytes = utf8.encode('new');
    const safe = CodeDiskFailure.safeWriteUnavailable;
    final failure = isA<WorkspaceFileException>().having(
        (error) => Platform.isWindows || error.failure == safe,
        'failure',
        isTrue);
    _fails<WorkspaceFileException>(
        () => transaction.compareAndWrite(
            canonicalRoot: root.resolveSymbolicLinksSync(),
            requestedPath: original.path,
            expectedDiskSha256: sha256.convert(utf8.encode('old')).toString(),
            bufferSha256: sha256.convert(bytes).toString(),
            bytes: bytes),
        failure);
    if (!Platform.isWindows) expect(original.readAsStringSync(), 'old');
    expect(escaped.readAsStringSync(), 'outside');
  });
}
