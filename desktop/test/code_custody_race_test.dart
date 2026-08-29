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

File _owned(File record, List<int> bytes) => File('${record.path}.fw-write.'
    '$pid.${'a' * 32}.${sha256.convert(bytes)}.tmp');

final class _Harness {
  _Harness() {
    root = _temp('code-race-session-');
    drafts = _temp('code-race-drafts-');
    file = File('${root.path}/lib/main.dart')
      ..parent.createSync(recursive: true)
      ..writeAsStringSync('baseline');
    session = CodeBufferSession(draftStore: CodeDraftStore(root: drafts))
      ..openWorkspace(root.path)
      ..recover()
      ..openFile(file.path);
  }
  late final Directory root, drafts;
  late final File file;
  late final CodeBufferSession session;
  OpenFile get active => session.openFiles[session.activeIndex];
  void edit(String text) =>
      session.snapshot((active..controller.text = text).path);
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

void main() {
  _targetValidationTests();
  _promptRevisionTests();
  _resetTests();
  _privateRootTests();
  _transactionReadTests();
  _batchRecoveryTests();
}

void _targetValidationTests() {
  for (final name in [
    'corrupt',
    'corrupt-candidate',
    'oversized',
    'path-mismatch'
  ]) {
    test('$name target stays byte exact before save', () {
      final source = _temp('code-target-source-');
      CodeDraftStore(root: source)
        ..save(workspaceRef: _workspace, draft: _draft('valid'))
        ..save(
            workspaceRef: _workspace,
            draft: _draft('other', path: 'lib/other.dart'));
      final valid = _record(source).readAsBytesSync();
      final bytes = switch (name) {
        'oversized' => List<int>.filled(1048577, 0x78),
        'path-mismatch' => _record(source, 'lib/other.dart').readAsBytesSync(),
        _ => utf8.encode('{'),
      };
      final root = _temp('code-target-$name-');
      final target = _record(root)
        ..parent.createSync(recursive: true)
        ..writeAsBytesSync(bytes);
      final candidate =
          name == 'corrupt-candidate' ? _owned(target, valid) : null;
      candidate?.writeAsBytesSync(valid);
      expect(
          () => CodeDraftStore(root: root)
              .save(workspaceRef: _workspace, draft: _draft('replacement')),
          throwsA(isA<CodeDraftStoreException>()),
          reason: name);
      expect(target.readAsBytesSync(), bytes, reason: name);
      if (candidate != null) {
        expect(candidate.readAsBytesSync(), valid, reason: name);
      }
    });
  }
}

void _promptRevisionTests() {
  for (final choice in [CloseChoice.save, CloseChoice.discard]) {
    test('A-B-A edit rejects pending ${choice.name}', () async {
      final harness = _Harness()..edit('A');
      final pending = Completer<CloseChoice>();
      final guard = UnsavedWorkGuard(
          session: harness.session, prompt: (_) => pending.future);
      final result = guard.requestNavigation('Chat');
      harness
        ..edit('B')
        ..edit('A');
      pending.complete(choice);
      expect(await result, isFalse);
      expect(harness.active.controller.text, 'A');
      expect(harness.active.dirty, isTrue);
      expect(harness.file.readAsStringSync(), 'baseline');
    });
  }
}

void _resetTests() {
  test('reset clears active selection in closed and recovering phases', () {
    final harness = _Harness();
    expect(harness.session.closeWorkspace(), isTrue);
    final closed = [harness.session.phase, harness.session.activeIndex];
    harness.session.openWorkspace(_temp('code-reset-next-').path);
    expect([
      closed,
      harness.session.phase,
      harness.session.activeIndex
    ], [
      [CodeSessionPhase.closed, -1],
      CodeSessionPhase.recovering,
      -1,
    ]);
  });
}

void _privateRootTests() {
  test('real lock-root junction refuses storage mutation', () {
    final root = _temp('code-lock-link-');
    final outside = _temp('code-lock-outside-');
    if (!_junction(Directory('${root.path}/.locks'), outside)) return;
    expect(
        () => CodeDraftStore(root: root)
            .save(workspaceRef: _workspace, draft: _draft('x')),
        throwsA(isA<CodeDraftStoreException>()));
    expect(outside.listSync(), isEmpty);
    expect(_record(root).existsSync(), isFalse);
  });

  test('real quarantine-root junction preserves target and orphan', () {
    final root = _temp('code-quarantine-link-');
    final store = CodeDraftStore(root: root);
    final stored = store.save(workspaceRef: _workspace, draft: _draft('prior'));
    final target = _record(root);
    final before = target.readAsBytesSync();
    final orphan = _owned(target, before)..writeAsBytesSync(before);
    final outside = _temp('code-quarantine-outside-');
    if (!_junction(Directory('${root.path}/.quarantine'), outside)) return;
    expect(() => store.load(workspaceRef: _workspace),
        throwsA(isA<CodeDraftStoreException>()));
    expect(target.readAsBytesSync(), before);
    expect(orphan.readAsBytesSync(), before);
    expect(outside.listSync(), isEmpty);
    expect(stored.draft.text, 'prior');
  });

  test('a second process observes the active per-record lock', () async {
    final r = _temp('code-record-lock-');
    final ready = File('${r.path}/ready'), release = File('${r.path}/go');
    final key = sha256.convert(utf8.encode('lib/main.dart')).toString();
    final source =
        "import 'dart:convert';import 'dart:io';import 'package:crypto/crypto.dart';import 'package:flywheel_desktop/services/code_draft_transaction.dart';void main(List<String> a){final target=File(a[0]+'/'+'$_workspace'+'/'+'$key.json');final bytes=utf8.encode(jsonEncode({'draft':{'buffer_sha256':'${sha256.convert(utf8.encode('first'))}','disk_sha256':'$_disk','path':'lib/main.dart','text':'first','updated_at':'2026-08-15T12:00:00.000Z'},'schema':'flywheel.desktop-code-draft/v1','workspace_ref':'$_workspace'}));final tx=CodeDraftTransaction(root:Directory(a[0]),workspaceRef:'$_workspace');tx.locked('$key',(){tx.write(target,bytes,valid:(raw,_)=>raw.isNotEmpty,beforeRename:(_){File(a[1]).writeAsStringSync('ready');while(!File(a[2]).existsSync())sleep(const Duration(milliseconds:10));});});}";
    final script = File('${r.path}/holder.dart')..writeAsStringSync(source);
    final cache = File(Platform.resolvedExecutable).parent.parent.parent.parent;
    final dart = File('${cache.path}/dart-sdk/bin/dart'
        '${Platform.isWindows ? '.exe' : ''}');
    final config = File('.dart_tool/package_config.json').absolute.path;
    final process = await Process.start(dart.path,
        ['--packages=$config', script.path, r.path, ready.path, release.path]);
    try {
      for (var i = 0; i < 3000 && !ready.existsSync(); i++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
      expect(ready.existsSync(), isTrue);
      try {
        CodeDraftStore(root: r)
            .save(workspaceRef: _workspace, draft: _draft('second'));
        fail('second process lock was not observed');
      } on CodeDraftStoreException catch (error) {
        expect(error.failure, CodeDraftFailure.storeBusy);
      }
    } finally {
      release.writeAsStringSync('release');
    }
    expect(await process.exitCode, 0);
    final stored = CodeDraftStore(root: r).load(workspaceRef: _workspace);
    expect(stored.single.draft.text, 'first');
  });
}

void _transactionReadTests() {
  test('session discard reads bytes and path from one retained handle', () {
    if (!Platform.isWindows) {
      markTestSkipped('Windows retained read-handle case');
      return;
    }
    final root = _temp('code-read-race-');
    final inside = Directory('${root.path}/inside')..createSync();
    final source = File('${inside.path}/target.dart')
      ..writeAsStringSync('safe');
    final canonicalSource = source.resolveSymbolicLinksSync();
    final held = File('${inside.path}/held.dart');
    var armed = false;
    final transaction = WorkspaceFileTransaction(afterHandleValidated: () {
      if (!armed) return;
      armed = false;
      source.renameSync(held.path);
      File(source.path).writeAsStringSync('replacement');
    });
    final session = CodeBufferSession(
        draftStore: CodeDraftStore(root: _temp('code-read-drafts-')),
        fileTransaction: transaction)
      ..openWorkspace(root.path)
      ..recover()
      ..openFile(source.path);
    session.openFiles.last.controller.text = 'dirty';
    session.snapshot(source.path);
    armed = true;
    expect(session.discard(source.path), isTrue);
    expect(session.openFiles.last.controller.text, 'safe');
    expect(session.openFiles.last.path, canonicalSource);
    expect(File(source.path).readAsStringSync(), 'replacement');
    expect(held.readAsStringSync(), 'safe');
  });
}

void _batchRecoveryTests() {
  test('failed second inspection preserves first already-saved journal', () {
    final root = _temp('code-batch-workspace-');
    final drafts = _temp('code-batch-drafts-');
    final a = File('${root.path}/lib/a.dart')
      ..parent.createSync(recursive: true)
      ..writeAsStringSync('a-base');
    final b = File('${root.path}/lib/b.dart')..writeAsStringSync('b-base');
    final first = CodeBufferSession(draftStore: CodeDraftStore(root: drafts))
      ..openWorkspace(root.path)
      ..recover()
      ..openFile(a.path);
    first.openFiles.last.controller.text = 'a-draft';
    first.snapshot(a.path);
    first.openFile(b.path);
    first.openFiles.last.controller.text = 'b-draft';
    first.snapshot(b.path);
    a.writeAsStringSync('a-draft', flush: true);
    first.dispose();
    var fail = true, reads = 0;
    final transaction = WorkspaceFileTransaction(afterHandleValidated: () {
      if (fail && ++reads == 2) {
        throw const WorkspaceFileException(CodeDiskFailure.unavailable);
      }
    });
    final second = CodeBufferSession(
        draftStore: CodeDraftStore(root: drafts), fileTransaction: transaction)
      ..openWorkspace(root.path);
    expect(second.recover(), isEmpty);
    expect(second.phase, CodeSessionPhase.recoveryBlocked);
    expect(
        CodeDraftStore(root: drafts).load(
            workspaceRef:
                workspace.workspaceReference(root.resolveSymbolicLinksSync())),
        hasLength(2));
    fail = false;
    reads = 0;
    expect(second.retryRecovery(), isTrue);
    expect(second.recoveryOutcomes.map((value) => value.kind),
        [CodeRecoveryKind.alreadySaved, CodeRecoveryKind.restored]);
    expect(second.openFiles.map((file) => file.controller.text),
        ['a-draft', 'b-draft']);
  });
}
