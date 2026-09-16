// chat_thread.dart — the conversation thread: user and assistant turns as
// source-addressable cards, streaming text as it arrives, fenced code rendered
// in mono cards, and receipt state preserved beside copy/bookmark actions.

import 'package:flutter/material.dart';

import '../models/chat.dart';
import '../theme/flywheel_theme.dart';
import 'chat_bubble.dart';
import 'chat_navigation_types.dart';

class ChatThreadJumpController extends ChangeNotifier {
  ChatNavTarget? _target;
  int _serial = 0;

  void jumpTo(ChatNavTarget target) {
    _target = target;
    _serial++;
    notifyListeners();
  }
}

class ChatThread extends StatefulWidget {
  final List<ChatMessage> messages;
  final ScrollController controller;
  final String conversationId;
  final List<String>? messageIds;
  final ChatThreadJumpController? jumpController;
  final ValueChanged<String>? onOpenUrl;
  final ValueChanged<ChatNavTarget>? onOpenLocalTarget;
  final ValueChanged<ChatNavTarget>? onBookmark;
  final Set<String> bookmarkedMessageIds;

  const ChatThread({
    super.key,
    required this.messages,
    required this.controller,
    this.conversationId = '',
    this.messageIds,
    this.jumpController,
    this.onOpenUrl,
    this.onOpenLocalTarget,
    this.onBookmark,
    this.bookmarkedMessageIds = const {},
  });

  @override
  State<ChatThread> createState() => _ChatThreadState();
}

class _ChatThreadState extends State<ChatThread> {
  final _messageKeys = <String, GlobalKey<ChatBubbleState>>{};
  int _lastJumpSerial = 0;
  String? _highlightedMessageId;

  @override
  void initState() {
    super.initState();
    widget.jumpController?.addListener(_handleJump);
  }

  @override
  void didUpdateWidget(ChatThread oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.jumpController, widget.jumpController)) {
      oldWidget.jumpController?.removeListener(_handleJump);
      widget.jumpController?.addListener(_handleJump);
    }
    _pruneKeys();
  }

  @override
  void dispose() {
    widget.jumpController?.removeListener(_handleJump);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    _pruneKeys();
    return SingleChildScrollView(
      controller: widget.controller,
      padding: const EdgeInsets.symmetric(
          horizontal: FwLayout.s5, vertical: FwLayout.s5),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        for (final (index, message) in widget.messages.indexed)
          ChatBubble(
            key: _keyFor(_messageId(index)),
            conversationId: widget.conversationId,
            message: message,
            messageId: _messageId(index),
            highlighted: _highlightedMessageId == _messageId(index),
            bookmarked: widget.bookmarkedMessageIds.contains(_messageId(index)),
            onOpenUrl: widget.onOpenUrl,
            onOpenLocalTarget: widget.onOpenLocalTarget,
            onBookmark: widget.onBookmark,
          ),
      ]),
    );
  }

  void _handleJump() {
    final controller = widget.jumpController;
    if (controller == null || controller._serial == _lastJumpSerial) return;
    _lastJumpSerial = controller._serial;
    final target = controller._target;
    if (target == null) return;
    setState(() => _highlightedMessageId = target.messageId);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final state = _messageKeys[target.messageId]?.currentState;
      if (state == null) return;
      Scrollable.ensureVisible(
        state.context,
        alignment: 0.08,
        duration: Duration.zero,
      );
      WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToAnchor(target));
    });
  }

  void _scrollToAnchor(ChatNavTarget target) {
    if (!mounted || target.offset == null || !widget.controller.hasClients) {
      return;
    }
    final anchor =
        _messageKeys[target.messageId]?.currentState?.sourceAnchorForOffset(target.offset);
    if (anchor == null) return;
    Scrollable.ensureVisible(
      anchor.context,
      alignment: 0.16,
      duration: Duration.zero,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) => _fineTuneAnchor(target));
  }

  void _fineTuneAnchor(ChatNavTarget target) {
    if (!mounted || target.offset == null || !widget.controller.hasClients) {
      return;
    }
    final anchor =
        _messageKeys[target.messageId]?.currentState?.sourceAnchorForOffset(target.offset);
    if (anchor == null) return;
    final scrollable = Scrollable.maybeOf(anchor.context);
    final viewportBox = scrollable?.context.findRenderObject() as RenderBox?;
    final anchorBox = anchor.context.findRenderObject() as RenderBox?;
    if (viewportBox == null || anchorBox == null) return;
    if (!viewportBox.hasSize || !anchorBox.hasSize) return;
    final position = widget.controller.position;
    final anchorTop = anchorBox.localToGlobal(Offset.zero, ancestor: viewportBox).dy;
    final desired = position.pixels + anchorTop +
        anchorBox.size.height * anchor.fraction -
        position.viewportDimension * 0.16;
    widget.controller.jumpTo(desired.clamp(0.0, position.maxScrollExtent));
  }

  String _messageId(int index) => index < (widget.messageIds?.length ?? 0)
      ? widget.messageIds![index]
      : widget.messages[index].id;

  GlobalKey<ChatBubbleState> _keyFor(String id) =>
      _messageKeys.putIfAbsent(id, GlobalKey<ChatBubbleState>.new);

  void _pruneKeys() {
    final live = {
      for (var i = 0; i < widget.messages.length; i++) _messageId(i)
    };
    _messageKeys.removeWhere((id, _) => !live.contains(id));
  }
}
