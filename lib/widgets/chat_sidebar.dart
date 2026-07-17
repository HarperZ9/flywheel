// chat_sidebar.dart — the conversation history rail: New chat, and the list of
// past chats (now durable), each selectable and deletable on hover. Kept out of
// the view so the shell stays small and the list is its own testable piece.

import 'package:flutter/material.dart';

import '../models/chat.dart';
import '../theme/flywheel_theme.dart';

class ChatSidebar extends StatelessWidget {
  final List<Conversation> conversations;
  final Conversation current;
  final bool streaming;
  final VoidCallback onNew;
  final ValueChanged<Conversation> onSelect;
  final ValueChanged<Conversation> onDelete;
  const ChatSidebar({
    super.key,
    required this.conversations,
    required this.current,
    required this.streaming,
    required this.onNew,
    required this.onSelect,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      width: 232,
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(right: BorderSide(color: t.hairline)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Padding(
          padding: const EdgeInsets.all(FwLayout.s3),
          child: OutlinedButton.icon(
            onPressed: streaming ? null : onNew,
            icon: const Icon(Icons.add_rounded, size: 16),
            label: const Text('New chat'),
            style: OutlinedButton.styleFrom(
                alignment: Alignment.centerLeft,
                padding: const EdgeInsets.symmetric(
                    horizontal: FwLayout.s3, vertical: FwLayout.s3)),
          ),
        ),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.symmetric(horizontal: FwLayout.s2),
            children: [
              for (final c in conversations)
                _ConvItem(
                  title: c.isEmpty ? 'New chat' : c.title,
                  selected: identical(c, current),
                  onTap: () => onSelect(c),
                  onDelete: streaming ? null : () => onDelete(c),
                ),
            ],
          ),
        ),
      ]),
    );
  }
}

class _ConvItem extends StatefulWidget {
  final String title;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback? onDelete;
  const _ConvItem(
      {required this.title,
      required this.selected,
      required this.onTap,
      this.onDelete});

  @override
  State<_ConvItem> createState() => _ConvItemState();
}

class _ConvItemState extends State<_ConvItem> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: Material(
        color: widget.selected ? t.panel : Colors.transparent,
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        child: InkWell(
          onTap: widget.onTap,
          borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
          child: Padding(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s3, vertical: 9),
            child: Row(children: [
              Expanded(
                child: Text(widget.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontSize: 13,
                        color: widget.selected ? t.ink : t.inkMuted,
                        fontWeight: widget.selected
                            ? FontWeight.w600
                            : FontWeight.w400)),
              ),
              if (_hover && widget.onDelete != null)
                GestureDetector(
                  onTap: widget.onDelete,
                  child: Padding(
                    padding: const EdgeInsets.only(left: 4),
                    child: Icon(Icons.close_rounded, size: 14, color: t.inkFaint),
                  ),
                ),
            ]),
          ),
        ),
      ),
    );
  }
}
