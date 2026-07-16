// chat_thread.dart — the conversation thread: user and assistant turns as
// bubbles, streaming text as it arrives, fenced code rendered in a mono card
// with copy, and a quiet 'verified' mark under an assistant turn that carried a
// receipt. Accountability is present but small; the conversation is the subject.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/chat.dart';
import '../theme/flywheel_theme.dart';

class ChatThread extends StatelessWidget {
  final List<ChatMessage> messages;
  final ScrollController controller;
  const ChatThread({super.key, required this.messages, required this.controller});

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      controller: controller,
      padding: const EdgeInsets.symmetric(horizontal: FwLayout.s5, vertical: FwLayout.s5),
      itemCount: messages.length,
      itemBuilder: (context, i) => _Bubble(message: messages[i]),
    );
  }
}

class _Bubble extends StatelessWidget {
  final ChatMessage message;
  const _Bubble({required this.message});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final isUser = message.isUser;
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isUser) _avatar(t, 'AI', t.verified),
          if (!isUser) const SizedBox(width: FwLayout.s3),
          Flexible(
            child: Column(
              crossAxisAlignment:
                  isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                Container(
                  constraints: const BoxConstraints(maxWidth: 640),
                  padding: const EdgeInsets.symmetric(
                      horizontal: FwLayout.s4, vertical: FwLayout.s3),
                  decoration: BoxDecoration(
                    color: isUser ? t.ground2 : t.panel,
                    borderRadius: BorderRadius.circular(FwLayout.radius),
                    border: Border.all(color: isUser ? Colors.transparent : t.hairline),
                  ),
                  child: _MessageBody(message: message),
                ),
                if (!isUser && !message.streaming) _footer(context, t),
              ],
            ),
          ),
          if (isUser) const SizedBox(width: FwLayout.s3),
          if (isUser) _avatar(t, 'You', t.inkMuted),
        ],
      ),
    );
  }

  Widget _avatar(FwTokens t, String label, Color color) => Container(
        width: 30,
        height: 30,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(9),
        ),
        child: Text(label == 'You' ? 'Y' : 'F',
            style: fwMono(t, size: 12, color: color)),
      );

  Widget _footer(BuildContext context, FwTokens t) {
    final receipt = message.receipt;
    return Padding(
      padding: const EdgeInsets.only(top: 6, left: 4),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        IconButton(
          onPressed: message.text.isEmpty
              ? null
              : () => Clipboard.setData(ClipboardData(text: message.text)),
          icon: const Icon(Icons.copy_rounded, size: 14),
          visualDensity: VisualDensity.compact,
          padding: EdgeInsets.zero,
          constraints: const BoxConstraints(minWidth: 26, minHeight: 20),
          color: t.inkFaint,
          tooltip: 'Copy',
        ),
        if (receipt != null) ...[
          const SizedBox(width: 6),
          Tooltip(
            message: 'Witnessed turn · receipt '
                '${(receipt['receipt_id'] ?? '').toString()}',
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.verified_outlined, size: 12, color: t.verified),
              const SizedBox(width: 4),
              Text('verified',
                  style: fwMono(t, size: 10.5, color: t.verified)),
            ]),
          ),
        ],
      ]),
    );
  }
}

/// Renders message text with fenced ``` code ``` blocks as mono cards; the rest
/// is selectable body text. A streaming turn shows a caret while it grows.
class _MessageBody extends StatelessWidget {
  final ChatMessage message;
  const _MessageBody({required this.message});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (message.text.isEmpty && message.streaming) {
      return Text('…', style: fwMono(t, size: 14, color: t.inkFaint));
    }
    final parts = _split(message.text);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final part in parts)
          part.code
              ? _CodeCard(code: part.text)
              : Padding(
                  padding: const EdgeInsets.symmetric(vertical: 1),
                  child: SelectableText(
                    part.text + (message.streaming && part == parts.last ? '▍' : ''),
                    style: TextStyle(
                        fontSize: 14, height: 1.5, color: t.inkSoft),
                  ),
                ),
      ],
    );
  }

  static List<_Part> _split(String text) {
    final parts = <_Part>[];
    final re = RegExp(r'```[\w-]*\n?([\s\S]*?)```', multiLine: true);
    var last = 0;
    for (final m in re.allMatches(text)) {
      if (m.start > last) {
        parts.add(_Part(text.substring(last, m.start).trim(), false));
      }
      parts.add(_Part((m.group(1) ?? '').trimRight(), true));
      last = m.end;
    }
    if (last < text.length) parts.add(_Part(text.substring(last).trim(), false));
    return parts.where((p) => p.text.isNotEmpty || p.code).toList();
  }
}

class _Part {
  final String text;
  final bool code;
  const _Part(this.text, this.code);
}

class _CodeCard extends StatelessWidget {
  final String code;
  const _CodeCard({required this.code});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(vertical: 6),
      decoration: BoxDecoration(
        color: t.ground2,
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        border: Border.all(color: t.hairline),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Align(
          alignment: Alignment.centerRight,
          child: IconButton(
            onPressed: () => Clipboard.setData(ClipboardData(text: code)),
            icon: const Icon(Icons.copy_rounded, size: 13),
            visualDensity: VisualDensity.compact,
            color: t.inkFaint,
            tooltip: 'Copy code',
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(
              FwLayout.s3, 0, FwLayout.s3, FwLayout.s3),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SelectableText(code, style: fwMono(t, size: 12.5, color: t.ink)),
          ),
        ),
      ]),
    );
  }
}
