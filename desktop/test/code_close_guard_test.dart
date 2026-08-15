import 'dart:async';
import 'dart:io';
import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/ide/code_buffer_session.dart';
import 'package:flywheel_desktop/ide/unsaved_work_guard.dart';
import 'package:flywheel_desktop/ide/workspace.dart' as workspace;
import 'package:flywheel_desktop/services/code_draft_store.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:flywheel_desktop/views/code_view.dart';
import 'package:flywheel_desktop/widgets/flywheel_nav.dart';
import 'journey_shell_test.dart';

Directory _temp(String name) {
  final value = Directory.systemTemp.createTempSync(name);
  addTearDown(() => value.deleteSync(recursive: true));
  return value;
}

class SessionHarness {
  SessionHarness({CodeDraftStore? store, CodeSaveFile? saveFile}) {
    root = _temp('code-session-');
    draftRoot = _temp('code-session-drafts-');
    file = File('${root.path}/lib/main.dart')
      ..parent.createSync(recursive: true)
      ..writeAsStringSync('baseline');
    session = CodeBufferSession(
        draftStore: store ?? CodeDraftStore(root: draftRoot),
        saveFile: saveFile);
    session.openWorkspace(root.path);
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
  _shellGuardTests();
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
    final conflict = restored.recover().single;
    expect([conflict.kind, conflict.diskText, conflict.draft.text],
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
  });

  test('disk write and readback failures remain dirty and block closure',
      () async {
    final failures = <CodeSaveFile>[
      (_, __) => throw StateError('injected'),
      (_, __) => workspace.SavedFile('0' * 64),
    ];
    for (final saveFile in failures) {
      final harness = SessionHarness(saveFile: saveFile)..edit('changed');
      final guard = UnsavedWorkGuard(
          session: harness.session, prompt: (_) async => CloseChoice.save);
      expect(await guard.requestApplicationExit(), isFalse);
      expect(harness.active.dirty, isTrue);
      expect(harness.session.drafts, hasLength(1));
    }
  });
}

void _prepareShellCode(ShellHarness harness) {
  final root = Directory('${harness.directory.path}/workspace')..createSync();
  final file = File('${root.path}/lib/main.dart')
    ..parent.createSync(recursive: true)
    ..writeAsStringSync('baseline');
  harness.code
    ..openWorkspace(root.path)
    ..openFile(file.path);
  final open = harness.code.openFiles.single;
  harness.code.snapshot((open..controller.text = 'dirty text').path);
}

void _shellGuardTests() {
  testWidgets('rail and FlywheelNav share guard and preserve the live session',
      (tester) async {
    final directory = _temp('code-shell-nav-');
    var choice = CloseChoice.cancel;
    final requests = <UnsavedWorkRequest>[];
    final harness = ShellHarness(directory, closePrompt: (request) async {
      requests.add(request);
      return choice;
    })
      ..replyReady();
    await tester.pumpWidget(harness.app());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Code'));
    await tester.pumpAndSettle();
    _prepareShellCode(harness);
    await tester.pump();
    final controller = harness.code.openFiles.single.controller;
    await tester.tap(find.text('Chat'));
    await tester.pumpAndSettle();
    expect(find.byType(CodeView), findsOneWidget);
    expect(requests.single.paths, ['lib/main.dart']);
    expect(harness.code.openFiles.single.controller, same(controller));
    expect(harness.code.drafts, hasLength(1));
    choice = CloseChoice.save;
    FlywheelNav.jump(tester.element(find.byType(CodeView)), 'Chat');
    await tester.pumpAndSettle();
    expect(find.byType(AgentView), findsOneWidget);
    expect(harness.code.openFiles.single.controller, same(controller));
    expect(harness.code.drafts, isEmpty);
    await unmount(tester);
  });

  testWidgets('app exit is guarded and direct unmount leaves a durable draft',
      (tester) async {
    final directory = _temp('code-shell-exit-');
    var choice = CloseChoice.cancel;
    var prompts = 0;
    final harness = ShellHarness(directory, closePrompt: (_) async {
      prompts++;
      return choice;
    })
      ..replyReady();
    await tester.pumpWidget(harness.app());
    await tester.pumpAndSettle();
    _prepareShellCode(harness);
    expect(await WidgetsBinding.instance.handleRequestAppExit(),
        AppExitResponse.cancel);
    choice = CloseChoice.discard;
    expect(await WidgetsBinding.instance.handleRequestAppExit(),
        AppExitResponse.exit);
    final open = harness.code.openFiles.single;
    open.controller.text = 'new dirty text';
    harness.code.snapshot(open.path);
    final ref = workspace.workspaceReference(harness.code.workspaceRoot!);
    await unmount(tester);
    expect(prompts, 2);
    final stored = CodeDraftStore(root: Directory('${directory.path}/code'))
        .load(workspaceRef: ref);
    expect(stored.single.text, 'new dirty text');
  });
}
