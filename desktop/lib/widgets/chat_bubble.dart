import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/chat.dart';
import '../models/evidence_state.dart';
import '../theme/flywheel_theme.dart';
import 'chat_markdown_body.dart';
import 'chat_navigation_types.dart';
import 'rowan_avatar.dart';
import 'turn_receipt.dart';

class ChatBubble extends StatefulWidget {
  final String conversationId;
  final ChatMessage message;
  final String messageId;
  final bool highlighted;
  final bool bookmarked;
  final ValueChanged<String>? onOpenUrl;
  final ValueChanged<ChatNavTarget>? onOpenLocalTarget;
  final ValueChanged<ChatNavTarget>? onBookmark;

  const ChatBubble({
    super.key,
    required this.conversationId,
    required this.message,
    required this.messageId,
    required this.highlighted,
    required this.bookmarked,
    this.onOpenUrl,
    this.onOpenLocalTarget,
    this.onBookmark,
  });

  @override
  State<ChatBubble> createState() => ChatBubbleState();
}

class ChatBubbleState extends State<ChatBubble> {
  bool _receiptOpen = false;
  final _bodyKey = GlobalKey<ChatMarkdownBodyState>();
  final _receiptFocus = FocusNode();
  ChatMessage get message => widget.message;

  @override
  void dispose() {
    _receiptFocus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final isUser = message.isUser;
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment:
            isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isUser) const RowanAvatar(),
          if (!isUser) const SizedBox(width: FwLayout.s3),
          Flexible(
            child: Column(
              crossAxisAlignment:
                  isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                Container(
                  constraints: const BoxConstraints(maxWidth: 680),
                  padding: const EdgeInsets.symmetric(
                      horizontal: FwLayout.s4, vertical: FwLayout.s3),
                  decoration: BoxDecoration(
                    color: isUser ? t.ground2 : t.panel,
                    borderRadius: BorderRadius.circular(FwLayout.radius),
                    border: Border.all(
                      color: widget.highlighted
                          ? t.drift
                          : isUser
                              ? Colors.transparent
                              : t.hairline,
                      width: widget.highlighted ? 1.5 : 1,
                    ),
                  ),
                  child: ChatMarkdownBody(
                    key: _bodyKey,
                    text: message.text,
                    streaming: message.streaming,
                    onOpenUrl: widget.onOpenUrl,
                    onOpenLocalTarget: widget.onOpenLocalTarget,
                  ),
                ),
                if (!message.streaming) _footer(context, t),
                if (_receiptOpen && message.receipt != null)
                  Container(
                    constraints: const BoxConstraints(maxWidth: 680),
                    padding: const EdgeInsets.only(top: FwLayout.s2),
                    child: TurnReceiptCard(receipt: message.receipt!),
                  ),
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
    final label = _receiptLabel(message.receiptState);
    final canBookmark = widget.onBookmark != null &&
        widget.conversationId.isNotEmpty &&
        isChatMessageId(widget.messageId);
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
        IconButton(
          onPressed: !canBookmark
              ? null
              : () => widget.onBookmark!(ChatNavTarget(
                    conversationId: widget.conversationId,
                    messageId: widget.messageId,
                  )),
          icon: Icon(
            widget.bookmarked
                ? Icons.bookmark_rounded
                : Icons.bookmark_border_rounded,
            size: 14,
          ),
          visualDensity: VisualDensity.compact,
          padding: EdgeInsets.zero,
          constraints: const BoxConstraints(minWidth: 26, minHeight: 20),
          color: t.inkFaint,
          tooltip: widget.bookmarked ? 'Remove bookmark' : 'Bookmark turn',
        ),
        const SizedBox(width: 6),
        if (!message.isUser)
          receipt == null
              ? Text(label, style: fwMono(t, size: 10.5, color: t.inkFaint))
              : _ReceiptButton(
                  label: label,
                  state: message.receiptState,
                  open: _receiptOpen,
                  focusNode: _receiptFocus,
                  onPressed: _toggleReceipt,
                ),
      ]),
    );
  }

  ChatMarkdownSourceAnchor? sourceAnchorForOffset(int? offset) {
    if (offset != null) {
      final anchor = _bodyKey.currentState?.sourceAnchorForOffset(offset);
      if (anchor != null) return anchor;
    }
    return ChatMarkdownSourceAnchor(context, 0);
  }

  void _toggleReceipt() => setState(() => _receiptOpen = !_receiptOpen);
}

class _ReceiptButton extends StatelessWidget {
  final String label;
  final ReceiptState state;
  final bool open;
  final FocusNode focusNode;
  final VoidCallback onPressed;

  const _ReceiptButton({
    required this.label,
    required this.state,
    required this.open,
    required this.focusNode,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Semantics(
      container: true,
      label: 'Receipt state $label',
      button: true,
      enabled: true,
      expanded: open,
      onTap: onPressed,
      excludeSemantics: true,
      child: TextButton(
        key: const ValueKey('chat-receipt-control'),
        focusNode: focusNode,
        onPressed: onPressed,
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll(Size(44, 44)),
          side: WidgetStateProperty.resolveWith((states) => BorderSide(
              color: states.contains(WidgetState.focused)
                  ? t.ink
                  : Colors.transparent,
              width: states.contains(WidgetState.focused) ? 2 : 1)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text(label,
              style: fwMono(t, size: 10.5, color: _receiptColor(t, state))),
          AnimatedRotation(
            turns: open ? 0.5 : 0,
            duration: MediaQuery.of(context).disableAnimations
                ? Duration.zero
                : const Duration(milliseconds: 180),
            child: Icon(Icons.expand_more, size: 12, color: t.inkFaint),
          ),
        ]),
      ),
    );
  }
}

String _receiptLabel(ReceiptState state) => switch (state) {
      ReceiptState.missing => 'missing',
      ReceiptState.presentUnchecked => 'Receipt not checked',
      ReceiptState.match => 'MATCH',
      ReceiptState.drift => 'DRIFT',
      ReceiptState.tampered => 'TAMPERED',
      ReceiptState.unverifiable => 'UNVERIFIABLE',
      ReceiptState.invalidResponse => 'invalid response',
    };

Color _receiptColor(FwTokens tokens, ReceiptState state) => switch (state) {
      ReceiptState.match => tokens.verified,
      ReceiptState.drift || ReceiptState.tampered => tokens.drift,
      ReceiptState.unverifiable => tokens.unverifiable,
      _ => tokens.inkFaint,
    };
