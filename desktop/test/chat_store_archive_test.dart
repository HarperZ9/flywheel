// Desktop history without silent drops (design 7.9, FW-13; I1, I19).
//
// The history file once kept the 60 newest conversations and dropped the
// rest with no marker, and an unreadable file was replaced by the next save.
// These tests pin the replacement: an append-only archive, a quarantine that
// never overwrites, a metadata-only loss record, and deletion by id across
// every file that can hold a conversation.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/controllers/chat_admission_controller.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/services/chat_draft_store.dart';
import 'package:flywheel_desktop/services/chat_store.dart';

Conversation _conversation(int n, {String? text}) => Conversation(
    id: 'c$n',
    title: 'topic $n',
    messages: [ChatMessage(role: 'user', text: text ?? 'question $n')]);

List<Conversation> _newestFirst(int count) =>
    [for (var n = count - 1; n >= 0; n--) _conversation(n)];

Directory _home() {
  final directory = Directory.systemTemp.createTempSync('chat-archive-');
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

Set<String> _ids(Iterable<Conversation> conversations) =>
    {for (final c in conversations) c.id};

List<File> _segments(Directory home) {
  final directory = Directory('${home.path}/chats-archive');
  if (!directory.existsSync()) return [];
  return directory.listSync().whereType<File>().toList();
}

void main() {
  test('61 conversations all survive across the active file and the archive',
      () {
    final home = _home();
    final store = ChatStore(file: File('${home.path}/chats.json'));
    expect(store.save(_newestFirst(61)), isTrue);

    final reopened = ChatStore(file: File('${home.path}/chats.json'));
    final active = reopened.load();
    final archived = reopened.loadArchived();
    expect(active, hasLength(60));
    expect(archived.single.id, 'c0');
    expect(_ids(active).union(_ids(archived)), _ids(_newestFirst(61)));
    expect(reopened.status.archivedCount, 1);
    expect(_segments(home), hasLength(1));
  });

  test('the window also holds the envelope under its byte bound', () {
    final home = _home();
    final store = ChatStore(file: File('${home.path}/chats.json'));
    final big = 'x' * (200 * 1024);
    final conversations = [
      for (var n = 5; n >= 0; n--) _conversation(n, text: '$big $n')
    ];
    expect(store.save(conversations), isTrue);
    final active = store.load();
    expect(File('${home.path}/chats.json').lengthSync(),
        lessThanOrEqualTo(ChatStore.windowBytes));
    expect(active.first.id, 'c5');
    expect(_ids(active).union(_ids(store.loadArchived())),
        _ids(conversations));
  });

  test('a rename failure between archive and active rewrite loses nothing',
      () {
    final home = _home();
    final file = File('${home.path}/chats.json');
    expect(ChatStore(file: file).save(_newestFirst(60)), isTrue);
    final failing = ChatStore(
        file: file,
        renameFile: (temporary, target) {
          if (target == file.path) {
            throw const FileSystemException('injected rename failure');
          }
          temporary.renameSync(target);
        });
    expect(failing.save([_conversation(60), ..._newestFirst(60)]), isFalse);

    final reopened = ChatStore(file: file);
    final active = reopened.load();
    final archived = reopened.loadArchived();
    expect(_ids(active), _ids(_newestFirst(60)));
    expect(_ids(active).intersection(_ids(archived)), isEmpty,
        reason: 'the archived copy of an active conversation is not shown');
    expect(reopened.archivedIds(), contains('c0'));
  });

  test('load keeps the active copy when a conversation exists twice', () {
    final home = _home();
    final file = File('${home.path}/chats.json');
    final store = ChatStore(file: file);
    expect(store.save(_newestFirst(61)), isTrue);
    final revised = _conversation(0, text: 'revised in the active file');
    expect(store.save([revised]), isTrue);

    final reopened = ChatStore(file: file);
    final c0 = reopened.load().singleWhere((c) => c.id == 'c0');
    expect(c0.messages.single.text, 'revised in the active file');
    expect(_ids(reopened.loadArchived()), isNot(contains('c0')));
  });

  test('the legacy bare-list format loads', () {
    final home = _home();
    final file = File('${home.path}/chats.json')
      ..writeAsStringSync(jsonEncode([_conversation(3).toJson()]));
    final loaded = ChatStore(file: file).load();
    expect(loaded.single.id, 'c3');
    expect(loaded.single.messages.single.text, 'question 3');
  });

  test('an unreadable active file is set aside byte for byte and kept', () {
    final home = _home();
    final file = File('${home.path}/chats.json');
    final bytes = utf8.encode('{"conversations": [ not json');
    file.writeAsBytesSync(bytes);
    final store = ChatStore(file: file);
    expect(store.load(), isEmpty);
    final setAside = store.quarantinedFiles();
    expect(setAside, hasLength(1));
    expect(setAside.single.path, contains('chats.unreadable-'));
    expect(setAside.single.readAsBytesSync(), bytes);
    expect(store.status.setAside, [setAside.single.path]);

    expect(store.save([_conversation(1)]), isTrue);
    expect(ChatStore(file: file).load().single.id, 'c1');
    expect(setAside.single.readAsBytesSync(), bytes,
        reason: 'the set-aside file is never touched again');
  });

  test('an active file that cannot be read pauses saving instead of '
      'replacing it', () {
    final home = _home();
    final file = File('${home.path}/chats.json');
    Directory(file.path).createSync();
    final store = ChatStore(file: file);
    expect(store.load(), isEmpty);
    expect(store.status.savingPaused, isTrue);
    expect(store.save([_conversation(1)]), isFalse);
    expect(Directory(file.path).existsSync(), isTrue);
  });

  test('an oversize conversation leaves a metadata-only loss record', () {
    final home = _home();
    final file = File('${home.path}/chats.json');
    final canary = 'LOSSCANARY${'y' * (1100 * 1024)}';
    final store = ChatStore(file: file);
    expect(store.save([_conversation(7, text: canary)]), isFalse);
    expect(store.status.oversizeConversation, 'c7');

    final loss = Directory('${home.path}/desktop/loss/v1');
    final records = loss.listSync().whereType<File>().toList();
    expect(records, hasLength(1));
    final text = records.single.readAsStringSync();
    expect(text, isNot(contains('LOSSCANARY')));
    final record = jsonDecode(text) as Map<String, dynamic>;
    expect(record['schema'], 'flywheel.desktop-loss/v1');
    expect(record['reason_code'], 'CONVERSATION_OVER_LIMIT');
    expect(record['conversation_ref'], 'c7');
    expect(record['original'], 'drafts');
    expect(file.existsSync(), isFalse, reason: 'nothing else was written');
  });

  test('an unreadable archive segment is skipped, reported and kept', () {
    final home = _home();
    final file = File('${home.path}/chats.json');
    expect(ChatStore(file: file).save(_newestFirst(61)), isTrue);
    final segment = _segments(home).single;
    segment.writeAsStringSync('not a segment');
    final store = ChatStore(file: file);
    expect(store.load(), hasLength(60));
    expect(store.loadArchived(), isEmpty);
    expect(store.status.skippedSegments, [segment.path]);
    expect(store.save([_conversation(61), ..._newestFirst(61)]), isTrue);
    expect(segment.readAsStringSync(), 'not a segment');
  });

  test('a new conversation never reuses an archived id', () {
    final home = _home();
    final file = File('${home.path}/chats.json');
    expect(ChatStore(file: file).save(_newestFirst(61)), isTrue);
    final history = ChatStore(file: file);
    final controller = ChatAdmissionController(history,
        ChatDraftStore(file: File('${home.path}/chat-drafts.json')))
      ..restore();
    controller.conversations.clear();
    expect(history.save(const []), isTrue);
    final reopened = ChatStore(file: file);
    final fresh = ChatAdmissionController(reopened,
        ChatDraftStore(file: File('${home.path}/chat-drafts.json')))
      ..restore();
    // c1 to c60 were deleted and c0 is archived: counting only the active
    // file would hand out c0 again and shadow the archived conversation.
    final id = fresh.blankConversation(null).id;
    expect(reopened.archivedIds(), {'c0'});
    expect(id, 'c1');
  });

  test('deleting a conversation removes it everywhere and it stays gone', () {
    final home = _home();
    final file = File('${home.path}/chats.json');
    final drafts = ChatDraftStore(file: File('${home.path}/chat-drafts.json'));
    expect(ChatStore(file: file).save(_newestFirst(61)), isTrue);
    // A crash between the archive write and the active rewrite leaves c5
    // in both the active file and a segment; a draft names it too.
    final archive = ChatStore(file: file).archive;
    archive.upsert([_conversation(5).toJson()]);
    final history = ChatStore(file: file);
    final controller = ChatAdmissionController(history, drafts)..restore();
    controller.changeDraft(
        controller.conversations.firstWhere((c) => c.id == 'c5'), 'unsent');
    expect(drafts.load().where((d) => d.conversationRef == 'c5'), isNotEmpty);

    final target = controller.conversations.firstWhere((c) => c.id == 'c5');
    expect(controller.deleteConversation(target), isTrue);

    final reopened = ChatStore(file: file);
    expect(_ids(reopened.load()), isNot(contains('c5')));
    expect(reopened.archivedIds(), isNot(contains('c5')));
    expect(drafts.load().where((d) => d.conversationRef == 'c5'), isEmpty);
    for (final segment in _segments(home)) {
      expect(segment.readAsStringSync(), isNot(contains('"c5"')));
    }
    final restored = ChatAdmissionController(reopened, drafts)..restore();
    expect(_ids(restored.conversations), isNot(contains('c5')));
  });

  test('an archived conversation can be deleted from the archive', () {
    final home = _home();
    final file = File('${home.path}/chats.json');
    final store = ChatStore(file: file);
    expect(store.save(_newestFirst(62)), isTrue);
    expect(_ids(store.loadArchived()), {'c0', 'c1'});
    expect(store.deleteConversation('c0', store.load()), isTrue);
    final reopened = ChatStore(file: file)..load();
    expect(_ids(reopened.loadArchived()), {'c1'});
    expect(reopened.status.archivedCount, 1);
  });

  test('a set-aside file can be removed whole, and only a set-aside file',
      () {
    final home = _home();
    final file = File('${home.path}/chats.json')..writeAsStringSync('[oops');
    final store = ChatStore(file: file)..load();
    final setAside = store.quarantinedFiles().single;
    expect(store.removeQuarantined(file), isFalse);
    expect(store.removeQuarantined(setAside), isTrue);
    expect(setAside.existsSync(), isFalse);
    expect(store.status.setAside, isEmpty);
  });
}
