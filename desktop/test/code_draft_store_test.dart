import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/ide/code_buffer_session.dart';
import 'package:flywheel_desktop/services/code_draft_store.dart';

const _workspace =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _disk =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
final _updated = DateTime.parse('2026-08-15T12:00:00.000Z');

Directory _temp(String name) {
  final value = Directory.systemTemp.createTempSync(name);
  addTearDown(() => value.deleteSync(recursive: true));
  return value;
}

CodeDraft _draft({String path = 'lib/main.dart', String? text}) {
  final source =
      text ?? 'λ = 1; // 100% literal, /source/path, api_key = from_env\n';
  return CodeDraft(
      path: path,
      diskSha256: _disk,
      bufferSha256: sha256.convert(utf8.encode(source)).toString(),
      text: source,
      updatedAt: _updated);
}

File _record(Directory root, String path) {
  final digest = sha256.convert(utf8.encode(path)).toString();
  return File('${root.path}/$_workspace/$digest.json');
}

void main() {
  _roundTripTests();
  _admissionTests();
  _corruptionTests();
  _boundTests();
  _atomicTests();
}

void _roundTripTests() {
  test('canonical record preserves exact source bytes and immutable custody',
      () {
    final root = _temp('code-draft-roundtrip-');
    final store = CodeDraftStore(root: root);
    final draft = _draft();
    store.save(workspaceRef: _workspace, draft: draft);
    final loaded = store.load(workspaceRef: _workspace);
    expect(loaded.single.path, 'lib/main.dart');
    expect(loaded.single.text, draft.text);
    expect(utf8.encode(loaded.single.text), utf8.encode(draft.text));
    expect(loaded.single.updatedAt, _updated);
    expect(() => loaded.add(draft), throwsUnsupportedError);
    final bytes = _record(root, draft.path).readAsBytesSync();
    expect(bytes, utf8.encode(jsonEncode(jsonDecode(utf8.decode(bytes)))));
  });

  test('delete requires exact buffer digest ownership', () {
    final root = _temp('code-draft-delete-');
    final store = CodeDraftStore(root: root)
      ..save(workspaceRef: _workspace, draft: _draft());
    expect(
        () => store.delete(
            workspaceRef: _workspace,
            path: 'lib/main.dart',
            expectedBufferSha256: _disk),
        throwsA(isA<CodeDraftStoreException>()));
    expect(store.load(workspaceRef: _workspace), hasLength(1));
    store.delete(
        workspaceRef: _workspace,
        path: 'lib/main.dart',
        expectedBufferSha256: _draft().bufferSha256);
    expect(store.load(workspaceRef: _workspace), isEmpty);
  });
}

void _admissionTests() {
  test('relative path admission rejects raw and encoded escape forms', () {
    const bad = [
      '',
      '.',
      '..',
      '../a',
      r'..\a',
      '/root/a',
      r'C:\root\a',
      r'\\server\share\a',
      'file:///root/a',
      'lib:a',
      '%2e%2e/a',
      '%2Froot/a',
      r'%5c%5cserver%5cshare%5ca',
    ];
    for (final path in bad) {
      expect(() => _draft(path: path), throwsA(isA<CodeDraftStoreException>()),
          reason: path);
    }
    expect(
        () => CodeDraftStore(root: _temp('code-draft-ref-'))
            .load(workspaceRef: 'wrong'),
        throwsA(isA<CodeDraftStoreException>()));
    expect(
        () => CodeDraft(
            path: 'lib/main.dart',
            diskSha256: _disk,
            bufferSha256: _disk,
            text: 'different',
            updatedAt: _updated),
        throwsA(isA<CodeDraftStoreException>()));
  });

  test('symlinked custody root is refused before an outside write', () {
    if (Platform.isWindows) return;
    final parent = _temp('code-draft-link-');
    final outside = Directory('${parent.path}/outside')..createSync();
    final link = Link('${parent.path}/drafts')..createSync(outside.path);
    final store = CodeDraftStore(root: Directory(link.path));
    expect(() => store.save(workspaceRef: _workspace, draft: _draft()),
        throwsA(isA<CodeDraftStoreException>()));
    expect(outside.listSync(), isEmpty);
  });

  test('session refuses a present symlink outside its workspace', () {
    if (Platform.isWindows) return;
    final root = _temp('code-outside-root-');
    final outside = _temp('code-outside-file-');
    final target = File('${outside.path}/target.dart')..writeAsStringSync('x');
    final link = Link('${root.path}/linked.dart')..createSync(target.path);
    final session = CodeBufferSession(
        draftStore: CodeDraftStore(root: _temp('code-outside-drafts-')))
      ..openWorkspace(root.path);
    expect(() => session.openFile(link.path),
        throwsA(isA<CodeSessionException>()));
    expect(target.readAsStringSync(), 'x');
  });
}

void _corruptionTests() {
  test('duplicate, noncanonical, malformed and oversized records fail closed',
      () {
    final root = _temp('code-draft-corrupt-');
    final store = CodeDraftStore(root: root);
    final file = _record(root, 'lib/main.dart');
    file.parent.createSync(recursive: true);
    for (final bytes in <List<int>>[
      utf8.encode('{"schema":"x","schema":"x"}'),
      utf8.encode('{ "schema": "x" }'),
      <int>[0xff, 0xfe],
      utf8.encode('{"extra":${jsonEncode('x' * 1048576)}}'),
      utf8.encode('{"extra":${'[' * 18}0${']' * 18}}'),
      utf8.encode(jsonEncode({'extra': List.filled(4097, 0)})),
    ]) {
      file.writeAsBytesSync(bytes);
      expect(() => store.load(workspaceRef: _workspace),
          throwsA(isA<CodeDraftStoreException>()));
    }
  });

  test('wrong workspace and digest fields fail without echoing source', () {
    final root = _temp('code-draft-fields-');
    final store = CodeDraftStore(root: root);
    store.save(workspaceRef: _workspace, draft: _draft());
    final file = _record(root, 'lib/main.dart');
    final raw = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final draft = raw['draft'] as Map<String, dynamic>;
    for (final invalid in [
      {...raw, 'workspace_ref': 'd' * 64},
      {...raw, 'schema': 'unknown'},
      {...raw, 'extra': true},
      {
        ...raw,
        'draft': {...draft, 'text': 1}
      },
      {
        ...raw,
        'draft': {...draft, 'disk_sha256': 'wrong'}
      },
    ]) {
      file.writeAsStringSync(jsonEncode(invalid));
      expect(() => store.load(workspaceRef: _workspace),
          throwsA(isA<CodeDraftStoreException>()));
    }
  });
}

void _boundTests() {
  test('complete record accepts exact byte bound and rejects one over', () {
    final root = _temp('code-draft-bound-');
    final store = CodeDraftStore(root: root);
    Map<String, dynamic> envelope(String text) => {
          'draft': {
            'buffer_sha256': sha256.convert(utf8.encode(text)).toString(),
            'disk_sha256': _disk,
            'path': 'lib/main.dart',
            'text': text,
            'updated_at': _updated.toIso8601String(),
          },
          'schema': 'flywheel.desktop-code-draft/v1',
          'workspace_ref': _workspace,
        };
    final overhead = utf8.encode(jsonEncode(envelope(''))).length;
    final exact = 'x' * (1048576 - overhead);
    store.save(workspaceRef: _workspace, draft: _draft(text: exact));
    final file = _record(root, 'lib/main.dart');
    expect(file.lengthSync(), 1048576);
    final before = file.readAsBytesSync();
    expect(
        () => store.save(
            workspaceRef: _workspace, draft: _draft(text: '$exact!')),
        throwsA(isA<CodeDraftStoreException>()));
    expect(file.readAsBytesSync(), before);
  });
}

void _atomicTests() {
  test('collision and pre-rename failures preserve prior bytes and temp owner',
      () {
    final root = _temp('code-draft-atomic-');
    final normal = CodeDraftStore(root: root)
      ..save(workspaceRef: _workspace, draft: _draft(text: 'prior'));
    final file = _record(root, 'lib/main.dart');
    final before = file.readAsBytesSync();
    final collision = File('${root.path}/collision.tmp')
      ..writeAsStringSync('x');
    final collisionStore =
        CodeDraftStore(root: root, temporaryFile: (_) => collision);
    expect(
        () => collisionStore.save(
            workspaceRef: _workspace, draft: _draft(text: 'next')),
        throwsA(isA<CodeDraftStoreException>()));
    expect(collision.readAsStringSync(), 'x');
    expect(file.readAsBytesSync(), before);
    File? owned;
    final failing = CodeDraftStore(
        root: root,
        temporaryFile: (_) => owned = File('${root.path}/owned.tmp'),
        beforeRename: (_) => throw StateError('injected'));
    expect(
        () =>
            failing.save(workspaceRef: _workspace, draft: _draft(text: 'next')),
        throwsA(isA<CodeDraftStoreException>()));
    expect(owned!.existsSync(), isFalse);
    expect(file.readAsBytesSync(), before);
    expect(normal.load(workspaceRef: _workspace).single.text, 'prior');
  });

  test('no-op, rename and corrupt readback restore the prior record', () {
    final root = _temp('code-draft-readback-');
    final outside = File('${_temp('code-draft-outside-').path}/outside.json')
      ..writeAsStringSync('outside');
    CodeDraftStore(root: root)
        .save(workspaceRef: _workspace, draft: _draft(text: 'prior'));
    final file = _record(root, 'lib/main.dart');
    final before = file.readAsBytesSync();
    for (final rename in <CodeDraftRenameFile>[
      (_, __) {},
      (_, __) => throw StateError('injected'),
      (temporary, target) {
        temporary.renameSync(target);
        File(target).writeAsStringSync('{}');
      },
      if (!Platform.isWindows)
        (temporary, target) {
          temporary.deleteSync();
          File(target).deleteSync();
          Link(target).createSync(outside.path);
        },
    ]) {
      final store = CodeDraftStore(root: root, renameFile: rename);
      expect(
          () =>
              store.save(workspaceRef: _workspace, draft: _draft(text: 'next')),
          throwsA(isA<CodeDraftStoreException>()));
      expect(file.readAsBytesSync(), before);
      expect(outside.readAsStringSync(), 'outside');
    }
  });
}
