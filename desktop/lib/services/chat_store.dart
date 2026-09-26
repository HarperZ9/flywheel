// Durable chat history without silent drops (design 7.9, FW-13).
//
// The active file keeps the newest conversations that fit the window: at
// most 60, and within 768 KiB and 3072 JSON nodes so a growing conversation
// has room. Older conversations move to archive segments before the active
// file shrinks; nothing is dropped. An active file that cannot be parsed is
// renamed aside byte for byte and never written again; one that cannot be
// read at all pauses saving so it is never replaced. A conversation too
// large for any envelope is refused with a metadata-only loss record, and
// its latest turn stays in drafts, where the caller already keeps it.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../client/gateway_auth.dart' show flywheelHome;
import '../models/chat.dart';
import 'chat_archive_store.dart';
import 'chat_history_status.dart';
import 'journey_session_store.dart';

class ChatStore {
  ChatStore({
    File? file,
    this.beforeRename,
    this.renameFile,
    this.temporaryFile,
    DateTime Function()? clock,
  })  : storageFile = file ?? _defaultFile(),
        _clock = clock ?? DateTime.now;

  static const maxConversations = 60;
  static const windowBytes = 768 * 1024;
  static const windowNodes = 3072;
  final File storageFile;
  final JourneyBeforeRename? beforeRename;
  final JourneyRenameFile? renameFile;
  final JourneyTemporaryFile? temporaryFile;
  final DateTime Function() _clock;
  final status = ChatHistoryStatus();
  late final ChatArchiveStore archive = ChatArchiveStore(
      Directory('${storageFile.parent.path}/chats-archive'),
      beforeRename: beforeRename,
      renameFile: renameFile,
      temporaryFile: temporaryFile,
      clock: _clock);
  var _activeIds = <String>{};

  static File _defaultFile() =>
      File('${flywheelHome()}${Platform.pathSeparator}chats.json');

  String get _stem {
    final name = storageFile.uri.pathSegments.last;
    return name.endsWith('.json') ? name.substring(0, name.length - 5) : name;
  }

  List<Conversation> load() {
    final active = _readActive();
    _activeIds = {for (final c in active) c.id};
    _refresh();
    return active;
  }

  bool save(List<Conversation> conversations) {
    if (status.savingPaused) return false;
    final items = [
      for (final c in conversations)
        if (!c.isEmpty) c.toJson()
    ];
    final sizes = [for (final item in items) chatJsonSize(item)];
    for (var index = 0; index < items.length; index++) {
      if (!chatFitsAlone(sizes[index])) {
        return _refuseOversize(items[index]['id'] as String);
      }
    }
    final split = _window(sizes);
    try {
      if (split < items.length) archive.upsert(items.sublist(split));
      writeJourneyLocalObject(storageFile,
          {'conversations': items.sublist(0, split), 'schema': chatHistorySchema},
          beforeRename: beforeRename,
          renameFile: renameFile,
          temporaryFile: temporaryFile);
    } catch (_) {
      debugPrint('chat history save failed');
      return false;
    }
    _activeIds = {for (final item in items.take(split)) item['id'] as String};
    status.oversizeConversation = null;
    _refresh();
    return true;
  }

  /// Archived conversations not in the active file, newest segment first,
  /// read on demand and never written back from here.
  List<Conversation> loadArchived() {
    final byId = archive.latestById(archive.read());
    final kept = [
      for (final entry in byId.entries)
        if (!_activeIds.contains(entry.key)) Conversation.fromJson(entry.value)
    ];
    return kept.reversed.toList(growable: false);
  }

  /// One archived conversation, so a draft that names it attaches to the
  /// whole conversation instead of starting an empty one with its id.
  Conversation? archivedConversation(String id) {
    if (!archive.ids().contains(id)) return null;
    final json = archive.latestById(archive.read())[id];
    return json == null ? null : Conversation.fromJson(json);
  }

  /// Every id kept in a readable archive segment.
  Set<String> archivedIds() => archive.ids();

  /// Removes `id` from every archive segment and rewrites the active file
  /// from `remaining` without it. False when any file could not be
  /// rewritten or checked; the banner says so.
  bool deleteConversation(String id, List<Conversation> remaining) {
    var complete = true;
    try {
      complete = archive.remove(id).isEmpty;
    } catch (_) {
      complete = false;
    }
    final saved = save([
      for (final c in remaining)
        if (c.id != id) c
    ]);
    complete = complete && saved;
    if (status.oversizeConversation == id) status.oversizeConversation = null;
    status.deleteIncomplete = !complete;
    _refresh();
    return complete;
  }

  /// Active files set aside as unreadable, which no load parses again.
  List<File> quarantinedFiles() {
    final prefix = '$_stem.unreadable-';
    final parent = storageFile.parent;
    if (!parent.existsSync()) return const [];
    return [
      for (final file in parent.listSync(followLinks: false).whereType<File>())
        if (file.uri.pathSegments.last.startsWith(prefix) &&
            file.path.endsWith('.json'))
          file
    ]..sort((a, b) => a.path.compareTo(b.path));
  }

  /// Deletes one set-aside file whole. Refuses any other file.
  bool removeQuarantined(File file) {
    final match = quarantinedFiles().where((f) => f.path == file.path);
    if (match.isEmpty) return false;
    try {
      match.single.deleteSync();
    } on FileSystemException {
      return false;
    }
    _refresh();
    return true;
  }

  List<Conversation> _readActive() {
    final type = FileSystemEntity.typeSync(storageFile.path, followLinks: false);
    if (type == FileSystemEntityType.notFound) return [];
    List<int> bytes;
    try {
      if (type != FileSystemEntityType.file) {
        throw const FileSystemException('history path is not a file');
      }
      bytes = storageFile.readAsBytesSync();
    } on FileSystemException {
      status.savingPaused = true;
      return [];
    }
    try {
      final decoded = jsonDecode(utf8.decode(bytes));
      final raw = decoded is List ? decoded : _readEnvelope();
      return [
        for (final conversation in raw)
          if (conversation is Map<String, dynamic>)
            Conversation.fromJson(conversation),
      ];
    } catch (_) {
      _quarantine();
      return [];
    }
  }

  List<dynamic> _readEnvelope() {
    final root = readJourneyLocalObject(storageFile);
    if (root.length != 2 ||
        root['schema'] != chatHistorySchema ||
        root['conversations'] is! List) {
      throw const FormatException('invalid chat history envelope');
    }
    return root['conversations'] as List;
  }

  void _quarantine() {
    final stamp = _clock().toUtc().toIso8601String().replaceAll(':', '');
    var target = File('${storageFile.parent.path}/$_stem.unreadable-$stamp.json');
    for (var n = 1; target.existsSync(); n++) {
      target = File(
          '${storageFile.parent.path}/$_stem.unreadable-$stamp-$n.json');
    }
    try {
      storageFile.renameSync(target.path);
    } on FileSystemException {
      status.savingPaused = true;
    }
  }

  int _window(List<ChatJsonSize> sizes) {
    final budget = ChatEnvelope(windowBytes, windowNodes);
    var count = 0;
    for (final size in sizes) {
      if (count == maxConversations) break;
      if (count > 0 && !budget.admits(size)) break;
      budget.add(size);
      count++;
    }
    return count;
  }

  bool _refuseOversize(String conversationRef) {
    writeChatLossRecord(storageFile.parent,
        conversationRef: conversationRef, at: _clock());
    status.oversizeConversation = conversationRef;
    status.changed();
    return false;
  }

  void _refresh() {
    status.setAside
      ..clear()
      ..addAll(quarantinedFiles().map((f) => f.path));
    try {
      status.archivedCount = archive.ids().difference(_activeIds).length;
      status.skippedSegments
        ..clear()
        ..addAll(archive.unreadable);
    } catch (_) {
      debugPrint('chat history archive could not be listed');
    }
    status.changed();
  }
}
