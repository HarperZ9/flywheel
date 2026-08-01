// chat_store.dart — durable conversations, so chats survive a restart. Lives at
// ~/.flywheel/chats.json beside desktop.json (overridable with FLYWHEEL_HOME).
// Never blocks launch: a missing or corrupt file is an empty history, not an
// error. Only non-empty conversations are kept, newest first, capped.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../models/chat.dart';

class ChatStore {
  static const _maxConversations = 60;

  static File _file() {
    final home = Platform.environment['FLYWHEEL_HOME'] ??
        '${Platform.environment['USERPROFILE'] ?? Platform.environment['HOME'] ?? '.'}'
            '${Platform.pathSeparator}.flywheel';
    return File('$home${Platform.pathSeparator}chats.json');
  }

  List<Conversation> load() {
    try {
      final f = _file();
      if (!f.existsSync()) return [];
      final j = jsonDecode(f.readAsStringSync());
      if (j is! List) return [];
      return [
        for (final c in j)
          if (c is Map<String, dynamic>) Conversation.fromJson(c),
      ];
    } catch (e) {
      debugPrint('chat history load failed, starting empty: $e');
      return [];
    }
  }

  void save(List<Conversation> conversations) {
    try {
      final kept = conversations.where((c) => !c.isEmpty).take(_maxConversations);
      final f = _file();
      f.parent.createSync(recursive: true);
      f.writeAsStringSync(jsonEncode([for (final c in kept) c.toJson()]));
    } catch (e) {
      debugPrint('chat history save failed: $e');
    }
  }
}
