import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/ide/code_buffer_session.dart';
import 'package:flywheel_desktop/ide/highlighter.dart';
import 'package:flywheel_desktop/ide/workspace.dart' as workspace;
import 'package:flywheel_desktop/ide/workspace_file_transaction.dart';
import 'package:flywheel_desktop/services/code_custody_io.dart';
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

CodeDraft _draft(String text, String path) => CodeDraft(
    path: path,
    diskSha256: _disk,
    bufferSha256: sha256.convert(utf8.encode(text)).toString(),
    text: text,
    updatedAt: _updated);

File _record(Directory root, String path) => File('${root.path}/$_workspace/'
    '${sha256.convert(utf8.encode(path))}.json');

void _makeLarge(File file) {
  file.parent.createSync(recursive: true);
  final handle = file.openSync(mode: FileMode.write);
  try {
    handle.setPositionSync(codeCustodyMaxBytes);
    handle.writeByteSync(0);
    handle.flushSync();
  } finally {
    handle.closeSync();
  }
}

final class _Handle implements CodeCustodyReadHandle {
  _Handle(this.length, this.chunks);
  final int length;
  final List<List<int>> chunks;
  int reads = 0;
  bool closed = false;

  @override
  void closeSync() => closed = true;
  @override
  int lengthSync() => length;
  @override
  List<int> readSync(int count) {
    reads++;
    return chunks.isEmpty ? const [] : chunks.removeAt(0);
  }
}

void main() {
  _boundedDraftReadTests();
  _workspaceReadTests();
  _recoveryCleanupTests();
  _recoveryDisposeTests();
}

void _boundedDraftReadTests() {
  test('oversized handle is rejected before reading and always closed', () {
    final handle = _Handle(codeCustodyMaxBytes + 1, const []);
    expect(() => readCodeCustodyFile(File('unused'), openHandle: (_) => handle),
        throwsFormatException);
    expect(handle.reads, 0);
    expect(handle.closed, isTrue);
  });

  test('single handle accepts short chunks only through exact EOF', () {
    final handle = _Handle(5, [
      [1, 2],
      [3],
      [4, 5],
      const [],
    ]);
    expect(readCodeCustodyFile(File('unused'), openHandle: (_) => handle),
        [1, 2, 3, 4, 5]);
    expect(handle.reads, 4);
    expect(handle.closed, isTrue);
  });

  for (final targetCase in [true, false]) {
    test('oversized ${targetCase ? 'target' : 'candidate'} is non-mutating',
        () {
      final root = _temp('code-bounded-draft-');
      final target = _record(root, 'lib/main.dart');
      final oversized = targetCase
          ? target
          : File('${target.path}.fw-write.$pid.${'a' * 32}.${'c' * 64}.tmp');
      _makeLarge(oversized);
      final before = oversized.statSync();
      final seen = <String>[];
      final store = CodeDraftStore(
          root: root,
          readFile: (file) {
            seen.add(file.path);
            return readCodeCustodyFile(file);
          });
      expect(
          () => store.save(
              workspaceRef: _workspace,
              draft: _draft('replacement', 'lib/main.dart')),
          throwsA(isA<CodeDraftStoreException>()));
      expect(seen, hasLength(1));
      expect(seen.single.replaceAll(r'\', '/'),
          endsWith(oversized.uri.pathSegments.last));
      expect(oversized.existsSync(), isTrue);
      expect(oversized.lengthSync(), before.size);
      expect(targetCase || !target.existsSync(), isTrue);
    });
  }
}

void _workspaceReadTests() {
  for (final extra in [0, 113]) {
    test('native read covers 16 MiB${extra == 0 ? '' : ' plus a short tail'}',
        () {
      if (!Platform.isWindows) {
        markTestSkipped('Windows ReadFile boundary case');
        return;
      }
      final root = _temp('code-native-read-');
      final size = 16 * 1048576 + extra;
      final bytes = List<int>.generate(size, (index) => index % 251);
      final file = File('${root.path}/large.bin')
        ..writeAsBytesSync(bytes, flush: true);
      final result = const WorkspaceFileTransaction().read(
          canonicalRoot: root.resolveSymbolicLinksSync(),
          requestedPath: file.path);
      expect(result.bytes.length, size);
      expect(result.sha256, sha256.convert(bytes).toString());
      final loaded = workspace.loadedFile(result);
      expect(loaded.readOnly, isTrue);
      expect(loaded.content.length, workspace.editableLimitBytes);
    });
  }
}

void _recoveryCleanupTests() {
  test('second cleanup failure retries the complete staged recovery', () {
    final root = _temp('code-cleanup-root-');
    final drafts = _temp('code-cleanup-drafts-');
    final files = ['a.dart', 'b.dart']
        .map((name) => File('${root.path}/lib/$name')
          ..parent.createSync(recursive: true)
          ..writeAsStringSync('base-$name'))
        .toList();
    final first = CodeBufferSession(draftStore: CodeDraftStore(root: drafts))
      ..openWorkspace(root.path)
      ..recover();
    for (var index = 0; index < files.length; index++) {
      first.openFile(files[index].path);
      first.openFiles[first.activeIndex].controller.text = 'saved-$index';
      first.snapshot(files[index].path);
      files[index].writeAsStringSync('saved-$index', flush: true);
    }
    first.dispose();
    var deletes = 0;
    var failSecond = true;
    final store = CodeDraftStore(
        root: drafts,
        deleteFile: (file) {
          deletes++;
          if (failSecond && deletes == 2) throw StateError('injected');
          file.deleteSync();
        });
    final second = CodeBufferSession(draftStore: store)
      ..openWorkspace(root.path);
    expect(second.recover(), isEmpty);
    expect(second.phase, CodeSessionPhase.recoveryBlocked);
    failSecond = false;
    expect(second.retryRecovery(), isTrue);
    expect(second.recoveryOutcomes, hasLength(2));
    expect(second.recoveryOutcomes.map((value) => value.kind),
        everyElement(workspace.CodeRecoveryKind.alreadySaved));
    expect(second.openFiles.map((file) => file.controller.text),
        ['saved-0', 'saved-1']);
    expect(
        store.load(
            workspaceRef:
                workspace.workspaceReference(root.resolveSymbolicLinksSync())),
        isEmpty);
  });
}

void _recoveryDisposeTests() {
  test('session dispose releases pending controllers and preserves journals',
      () {
    final root = _temp('code-dispose-root-');
    final drafts = _temp('code-dispose-drafts-');
    final files = ['a.dart', 'b.dart']
        .map((name) => File('${root.path}/lib/$name')
          ..parent.createSync(recursive: true)
          ..writeAsStringSync('base-$name'))
        .toList();
    final first = CodeBufferSession(draftStore: CodeDraftStore(root: drafts))
      ..openWorkspace(root.path)
      ..recover();
    for (var index = 0; index < files.length; index++) {
      first.openFile(files[index].path);
      first.openFiles[first.activeIndex].controller.text = 'saved-$index';
      first.snapshot(files[index].path);
      files[index].writeAsStringSync('saved-$index', flush: true);
    }
    first.dispose();
    final created = <Object>{};
    final disposed = <Object>{};
    void allocations(ObjectEvent event) {
      if (event.object is! CodeEditingController) return;
      if (event is ObjectCreated) created.add(event.object);
      if (event is ObjectDisposed) disposed.add(event.object);
    }

    FlutterMemoryAllocations.instance.addListener(allocations);
    addTearDown(
        () => FlutterMemoryAllocations.instance.removeListener(allocations));
    final failing = CodeDraftStore(
        root: drafts, deleteFile: (_) => throw StateError('injected'));
    final second = CodeBufferSession(draftStore: failing)
      ..openWorkspace(root.path);
    expect(second.recover(), isEmpty);
    expect(second.phase, CodeSessionPhase.recoveryBlocked);
    expect(created, hasLength(2));
    second.dispose();
    expect(disposed.intersection(created), hasLength(2));
    final workspaceRef =
        workspace.workspaceReference(root.resolveSymbolicLinksSync());
    expect(CodeDraftStore(root: drafts).load(workspaceRef: workspaceRef),
        hasLength(2));
    final fresh = CodeBufferSession(draftStore: CodeDraftStore(root: drafts))
      ..openWorkspace(root.path);
    expect(fresh.recover(), hasLength(2));
    expect(fresh.drafts, isEmpty);
    fresh.dispose();
  });
}
