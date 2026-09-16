import 'package:flutter/material.dart';

import '../models/chat.dart';
import 'chat_sidebar.dart';

Future<void> showChatConversationSheet(
  BuildContext context, {
  required List<Conversation> conversations,
  required Conversation current,
  required bool streaming,
  required VoidCallback onNew,
  required ValueChanged<Conversation> onSelect,
  required ValueChanged<Conversation> onDelete,
}) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      constraints: const BoxConstraints(maxWidth: 400),
      builder: (_) => DraggableScrollableSheet(
        initialChildSize: 0.55,
        minChildSize: 0.3,
        maxChildSize: 0.85,
        expand: false,
        builder: (sheetContext, ctrl) => ChatSidebar(
          conversations: conversations,
          current: current,
          streaming: streaming,
          scrollController: ctrl,
          onNew: () {
            onNew();
            Navigator.of(sheetContext).pop();
          },
          onSelect: (conversation) {
            onSelect(conversation);
            Navigator.of(sheetContext).pop();
          },
          onDelete: onDelete,
        ),
      ),
    );
