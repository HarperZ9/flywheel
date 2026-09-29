// Archive segments for chat history (design 7.9, FW-13).
//
// Conversations beyond the active window move here instead of being dropped.
// Each segment is `<home>/chats-archive/<yyyymm>-<n>.json` in the same
// envelope as the active file and under the same 1 MiB bound. A segment is
// written, renamed and verified before the active file shrinks, so a crash
// in between leaves a conversation in both places, never in neither.
//
// One copy per id is the goal: a newer copy is written first, then older
// copies are removed from other segments. A reader that finds two copies
// keeps the one in the later segment. A segment that cannot be read is
// skipped, reported and never rewritten.

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';

import 'journey_session_store.dart';

const chatHistorySchema = 'flywheel.desktop-chat-history/v1';
final _segmentName = RegExp(r'^(\d{6})-(\d{1,9})\.json$');

typedef ChatJsonSize = ({int bytes, int nodes, int depth});

/// Size of one conversation as the local store's guard counts it.
ChatJsonSize chatJsonSize(Object? value) {
  var nodes = 0;
  int visit(Object? item, int depth) {
    nodes++;
    var deepest = depth;
    final children = item is Map ? item.values : (item is List ? item : null);
    for (final child in children ?? const []) {
      deepest = max(deepest, visit(child, depth + 1));
    }
    return deepest;
  }

  final depth = visit(value, 0);
  return (bytes: utf8.encode(jsonEncode(value)).length, nodes: nodes, depth: depth);
}

/// The room left in one history envelope as conversations are added.
class ChatEnvelope {
  ChatEnvelope(this.maxBytes, this.maxNodes);
  static final _baseBytes = utf8
      .encode(jsonEncode({'conversations': [], 'schema': chatHistorySchema}))
      .length;
  final int maxBytes;
  final int maxNodes;
  var bytes = _baseBytes;
  var nodes = 3;
  var count = 0;

  bool admits(ChatJsonSize size) =>
      bytes + size.bytes + (count > 0 ? 1 : 0) <= maxBytes &&
      nodes + size.nodes <= maxNodes &&
      2 + size.depth <= journeyLocalMaxDepth;

  void add(ChatJsonSize size) {
    bytes += size.bytes + (count > 0 ? 1 : 0);
    nodes += size.nodes;
    count++;
  }
}

/// Whether one conversation fits an envelope of its own.
bool chatFitsAlone(ChatJsonSize size) =>
    ChatEnvelope(journeyLocalMaxBytes, journeyLocalMaxNodes).admits(size);

class ChatArchiveSegment {
  ChatArchiveSegment(this.file, this.month, this.number, this.conversations);
  final File file;
  final int month;
  final int number;

  /// Null when the segment could not be read.
  final List<Map<String, dynamic>>? conversations;
  bool get readable => conversations != null;
}

class ChatArchiveStore {
  ChatArchiveStore(this.directory,
      {this.beforeRename,
      this.renameFile,
      this.temporaryFile,
      DateTime Function()? clock})
      : _clock = clock ?? DateTime.now;

  final Directory directory;
  final JourneyBeforeRename? beforeRename;
  final JourneyRenameFile? renameFile;
  final JourneyTemporaryFile? temporaryFile;
  final DateTime Function() _clock;
  Map<String, String>? _digests;
  var _unreadable = <String>[];

  /// Every segment, oldest first; unreadable ones carry no conversations.
  List<ChatArchiveSegment> read() {
    final found = <ChatArchiveSegment>[];
    final entries = directory.existsSync()
        ? directory.listSync(followLinks: false).whereType<File>()
        : const <File>[];
    for (final file in entries) {
      final match = _segmentName.firstMatch(file.uri.pathSegments.last);
      if (match == null) continue;
      found.add(ChatArchiveSegment(file, int.parse(match.group(1)!),
          int.parse(match.group(2)!), _readSegment(file)));
    }
    found.sort((a, b) => a.month != b.month
        ? a.month.compareTo(b.month)
        : a.number.compareTo(b.number));
    _unreadable = [for (final s in found) if (!s.readable) s.file.path];
    _digests = {
      for (final entry in latestById(found).entries) entry.key: _digest(entry.value)
    };
    return found;
  }

  /// Paths of segments that could not be read at the last read.
  List<String> get unreadable {
    if (_digests == null) read();
    return List.unmodifiable(_unreadable);
  }

  /// One copy per id; a later segment wins over an earlier one.
  Map<String, Map<String, dynamic>> latestById(
      List<ChatArchiveSegment> segments) {
    final byId = <String, Map<String, dynamic>>{};
    for (final segment in segments.where((s) => s.readable)) {
      for (final conversation in segment.conversations!) {
        final id = conversation['id'];
        if (id is String) byId[id] = conversation;
      }
    }
    return byId;
  }

  Set<String> ids() {
    if (_digests == null) read();
    return Set.unmodifiable(_digests!.keys);
  }

  /// Stores each conversation unless an identical copy is already kept.
  /// Throws when a segment cannot be written; nothing is removed before the
  /// new copies are durable.
  void upsert(List<Map<String, dynamic>> incoming) {
    if (_digests == null) read();
    final pending = [
      for (final c in incoming)
        if (_digests![c['id']] != _digest(c)) c
    ];
    if (pending.isEmpty) return;
    final segments = read();
    final pendingIds = {for (final c in pending) c['id']};
    final losing = <ChatArchiveSegment>[];
    for (final segment in segments.where((s) => s.readable)) {
      final before = segment.conversations!.length;
      segment.conversations!.removeWhere((c) => pendingIds.contains(c['id']));
      if (segment.conversations!.length != before) losing.add(segment);
    }
    final gaining = _place(segments, pending);
    for (final segment in gaining) {
      _write(segment);
    }
    for (final segment in losing.where((s) => !gaining.contains(s))) {
      _write(segment);
    }
    read();
  }

  /// Removes every stored copy of `id` from the segments that can be read.
  /// Returns the paths of segments that could not be checked.
  List<String> remove(String id) {
    for (final segment in read().where((s) => s.readable)) {
      final before = segment.conversations!.length;
      segment.conversations!.removeWhere((c) => c['id'] == id);
      if (segment.conversations!.length != before) _write(segment);
    }
    read();
    return unreadable;
  }

  List<ChatArchiveSegment> _place(
      List<ChatArchiveSegment> segments, List<Map<String, dynamic>> pending) {
    final gaining = <ChatArchiveSegment>[];
    var target = segments.isNotEmpty && segments.last.readable
        ? segments.last
        : null;
    var budget = target == null ? null : _budget(target);
    for (final conversation in pending) {
      final size = chatJsonSize(conversation);
      if (target == null || !budget!.admits(size)) {
        target = _next(segments);
        segments.add(target);
        budget = ChatEnvelope(journeyLocalMaxBytes, journeyLocalMaxNodes);
        if (!budget.admits(size)) {
          throw const JourneyLocalStoreException(
              JourneyLocalFailure.invalidRecord);
        }
      }
      target.conversations!.add(conversation);
      budget.add(size);
      if (!gaining.contains(target)) gaining.add(target);
    }
    return gaining;
  }

  ChatEnvelope _budget(ChatArchiveSegment segment) {
    final budget = ChatEnvelope(journeyLocalMaxBytes, journeyLocalMaxNodes);
    for (final conversation in segment.conversations!) {
      budget.add(chatJsonSize(conversation));
    }
    return budget;
  }

  ChatArchiveSegment _next(List<ChatArchiveSegment> segments) {
    final now = _clock().toUtc();
    var month = now.year * 100 + now.month;
    if (segments.isNotEmpty && segments.last.month > month) {
      month = segments.last.month;
    }
    final number = segments
        .where((s) => s.month == month)
        .fold(0, (highest, s) => max(highest, s.number));
    final name = '$month-${number + 1}.json';
    return ChatArchiveSegment(
        File('${directory.path}/$name'), month, number + 1, []);
  }

  void _write(ChatArchiveSegment segment) {
    if (segment.conversations!.isEmpty) {
      if (segment.file.existsSync()) segment.file.deleteSync();
      return;
    }
    writeJourneyLocalObject(segment.file,
        {'conversations': segment.conversations, 'schema': chatHistorySchema},
        beforeRename: beforeRename,
        renameFile: renameFile,
        temporaryFile: temporaryFile);
  }

  List<Map<String, dynamic>>? _readSegment(File file) {
    try {
      final root = readJourneyLocalObject(file);
      final list = root['conversations'];
      if (root.length != 2 ||
          root['schema'] != chatHistorySchema ||
          list is! List) {
        return null;
      }
      return [
        for (final item in list)
          if (item is Map<String, dynamic>) Map<String, dynamic>.of(item)
      ];
    } catch (_) {
      return null;
    }
  }
}

String _digest(Map<String, dynamic> conversation) =>
    sha256.convert(utf8.encode(jsonEncode(_sorted(conversation)))).toString();

Object? _sorted(Object? value) {
  if (value is Map) {
    final keys = value.keys.map((k) => '$k').toList()..sort();
    return {for (final key in keys) key: _sorted(value[key])};
  }
  if (value is List) return [for (final item in value) _sorted(item)];
  return value;
}
