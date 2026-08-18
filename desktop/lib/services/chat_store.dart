import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../models/chat.dart';
import 'journey_session_store.dart';

const _historySchema = 'flywheel.desktop-chat-history/v1';

class ChatStore {
  ChatStore({
    File? file,
    this.beforeRename,
    this.renameFile,
    this.temporaryFile,
  }) : storageFile = file ?? _defaultFile();

  static const _maxConversations = 60;
  final File storageFile;
  final JourneyBeforeRename? beforeRename;
  final JourneyRenameFile? renameFile;
  final JourneyTemporaryFile? temporaryFile;

  static File _defaultFile() {
    final home = Platform.environment['FLYWHEEL_HOME'] ??
        '${Platform.environment['USERPROFILE'] ?? Platform.environment['HOME'] ?? '.'}'
            '${Platform.pathSeparator}.flywheel';
    return File('$home${Platform.pathSeparator}chats.json');
  }

  List<Conversation> load() {
    if (!storageFile.existsSync()) return [];
    try {
      final decoded = jsonDecode(storageFile.readAsStringSync());
      final raw = decoded is List ? decoded : _readEnvelope();
      return [
        for (final conversation in raw)
          if (conversation is Map<String, dynamic>)
            Conversation.fromJson(conversation),
      ];
    } catch (_) {
      debugPrint('chat history load failed; starting empty');
      return [];
    }
  }

  List<dynamic> _readEnvelope() {
    final root = readJourneyLocalObject(storageFile);
    if (root.length != 2 ||
        root['schema'] != _historySchema ||
        root['conversations'] is! List) {
      throw const FormatException('invalid chat history envelope');
    }
    return root['conversations'] as List;
  }

  bool save(List<Conversation> conversations) {
    try {
      final kept = conversations
          .where((conversation) => !conversation.isEmpty)
          .take(_maxConversations)
          .map((conversation) => conversation.toJson())
          .toList(growable: false);
      writeJourneyLocalObject(
          storageFile, {'conversations': kept, 'schema': _historySchema},
          beforeRename: beforeRename,
          renameFile: renameFile,
          temporaryFile: temporaryFile);
      return true;
    } catch (_) {
      debugPrint('chat history save failed');
      return false;
    }
  }
}
