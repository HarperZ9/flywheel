// What chat history could not do, kept where the history banner can say it
// (design 7.9, I1). Nothing here holds conversation text: paths of files set
// aside, a conversation id, and counts.

import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';

import 'journey_session_store.dart';

const chatLossSchema = 'flywheel.desktop-loss/v1';
const chatLossOverLimit = 'CONVERSATION_OVER_LIMIT';

class ChatHistoryStatus extends ChangeNotifier {
  /// Active history files that could not be read and were renamed aside.
  final setAside = <String>[];

  /// Archive segments that could not be read; they stay where they are.
  final skippedSegments = <String>[];

  /// The active file exists but could not be read or set aside, so saving is
  /// refused rather than replacing it.
  bool savingPaused = false;

  /// The conversation whose last save was refused because it is over the
  /// history bound; its latest turn stays in drafts.
  String? oversizeConversation;

  /// A delete that did not reach every file that holds the conversation.
  bool deleteIncomplete = false;

  /// Conversations kept in the archive and not in the active file.
  int archivedCount = 0;

  bool get hasNotice =>
      setAside.isNotEmpty ||
      skippedSegments.isNotEmpty ||
      savingPaused ||
      oversizeConversation != null ||
      deleteIncomplete;

  void changed() => notifyListeners();
}

/// Writes one metadata-only loss record under `<home>/desktop/loss/v1/`
/// before a save is refused for size, so the owner can see what history
/// could not keep and where the original still is. Returns the file, or null
/// when the record itself could not be written.
File? writeChatLossRecord(Directory home,
    {required String conversationRef, required DateTime at}) {
  final directory = Directory('${home.path}/desktop/loss/v1');
  final stamp = at.toUtc().toIso8601String().replaceAll(':', '');
  final suffix = Random.secure().nextInt(1 << 32).toRadixString(16);
  final file = File('${directory.path}/$stamp-$suffix.json');
  try {
    writeJourneyLocalObject(file, {
      'at': at.toUtc().toIso8601String(),
      'conversation_ref': conversationRef,
      'items': 1,
      'original': 'drafts',
      'reason_code': chatLossOverLimit,
      'schema': chatLossSchema,
      'store': 'S13',
    });
    return file;
  } catch (_) {
    debugPrint('chat history loss record could not be written');
    return null;
  }
}
