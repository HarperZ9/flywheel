import 'dart:async';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../assistant/rowan_action_cue_complete_ids.dart';
import '../assistant/rowan_action_cue_controller.dart';
import '../assistant/rowan_action_cue_hash.dart';
import '../assistant/rowan_action_cue_models.dart';
import '../models/chat.dart';
import '../theme/flywheel_theme.dart';
import 'chat_navigation_panel.dart';
import 'chat_navigation_projection.dart';
import 'chat_navigation_types.dart';
import 'chat_thread.dart';

class ChatWorkspaceController {
  void Function({bool force})? _scrollToLatest;
  void Function(ChatTarget target)? _jumpToTarget;

  void scrollToLatestIfFollowing() => _scrollToLatest?.call(force: false);
  void scrollToLatest() => _scrollToLatest?.call(force: true);
  void jumpTo(ChatTarget target) => _jumpToTarget?.call(target);
  void dispose() {
    _scrollToLatest = null;
    _jumpToTarget = null;
  }
}

class ChatWorkspace extends StatefulWidget {
  final Conversation conversation;
  final ChatWorkspaceController controller;
  final VoidCallback onConversationChanged;
  final RowanActionCueController? actionCueController;

  const ChatWorkspace({
    super.key,
    required this.conversation,
    required this.controller,
    required this.onConversationChanged,
    this.actionCueController,
  });

  @override
  State<ChatWorkspace> createState() => _ChatWorkspaceState();
}

class _ChatWorkspaceState extends State<ChatWorkspace> {
  final _scroll = ScrollController();
  final _jump = ChatThreadJumpController();
  bool _followLatest = true;
  ChatTarget? _lastTarget;
  var _searchCommitSerial = 0;

  @override
  void initState() {
    super.initState();
    widget.controller._scrollToLatest = _scrollToLatest;
    widget.controller._jumpToTarget = _jumpToLocal;
    _scroll.addListener(_trackReadingPosition);
    WidgetsBinding.instance
        .addPostFrameCallback((_) => _scrollToLatest(force: true));
  }

  @override
  void didUpdateWidget(ChatWorkspace oldWidget) {
    super.didUpdateWidget(oldWidget);
    widget.controller._scrollToLatest = _scrollToLatest;
    widget.controller._jumpToTarget = _jumpToLocal;
    if (oldWidget.conversation.id != widget.conversation.id) {
      _followLatest = true;
      _lastTarget = null;
      WidgetsBinding.instance
          .addPostFrameCallback((_) => _scrollToLatest(force: true));
    }
  }

  @override
  void dispose() {
    if (widget.controller._scrollToLatest == _scrollToLatest) {
      widget.controller._scrollToLatest = null;
      widget.controller._jumpToTarget = null;
    }
    _scroll.removeListener(_trackReadingPosition);
    _jump.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final snapshot =
        chatNavigationSnapshotFromConversation(widget.conversation);
    return LayoutBuilder(builder: (context, constraints) {
      final wide = constraints.maxWidth >= 980;
      final thread = _thread();
      if (wide) {
        return Row(children: [
          Expanded(child: thread),
          Container(
            width: 340,
            padding: const EdgeInsets.fromLTRB(
                0, FwLayout.s4, FwLayout.s4, FwLayout.s4),
            child: _panel(snapshot),
          ),
        ]);
      }
      return Stack(children: [
        thread,
        Positioned(
            top: FwLayout.s3, right: FwLayout.s3, child: _navButton(snapshot)),
      ]);
    });
  }

  Widget _thread() {
    final bookmarked = {
      for (final mark in widget.conversation.bookmarks) mark.target.messageId
    };
    return Stack(children: [
      NotificationListener<UserScrollNotification>(
        onNotification: (_) {
          _trackReadingPosition();
          return false;
        },
        child: ChatThread(
          conversationId: widget.conversation.id,
          messages: widget.conversation.messages,
          controller: _scroll,
          jumpController: _jump,
          bookmarkedMessageIds: bookmarked,
          onOpenUrl: _openUrl,
          onOpenLocalTarget: _jumpToLocal,
          onBookmark: _toggleBookmark,
        ),
      ),
      if (!_followLatest)
        Positioned(
          right: FwLayout.s4,
          bottom: FwLayout.s4,
          child: FilledButton.icon(
            onPressed: () => _scrollToLatest(force: true),
            icon: const Icon(Icons.south_rounded, size: 16),
            label: const Text('Return to latest'),
          ),
        ),
    ]);
  }

  Widget _panel(ChatNavigationSnapshot snapshot) => ChatNavigationPanel(
        snapshot: snapshot,
        conversationId: widget.conversation.id,
        notes: widget.conversation.notes,
        sourceReference: _lastTarget == null
            ? null
            : chatNoteReference(_lastTarget!, label: 'source'),
        onNotesChanged: _updateNotes,
        onTargetSelected: _jumpToLocal,
        onOpenUrl: _openUrl,
        onSearchCommitted: _searchCommitted,
        onSourceJump: _sourceJumped,
      );

  Widget _navButton(ChatNavigationSnapshot snapshot) => FilledButton.icon(
        onPressed: () => _showNavigation(snapshot),
        icon: const Icon(Icons.manage_search_rounded, size: 16),
        label: const Text('Navigate'),
      );

  void _showNavigation(ChatNavigationSnapshot snapshot) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      constraints: const BoxConstraints(maxWidth: 440),
      builder: (_) => DraggableScrollableSheet(
        initialChildSize: 0.75,
        minChildSize: 0.35,
        maxChildSize: 0.92,
        expand: false,
        builder: (_, __) => Padding(
          padding: const EdgeInsets.all(FwLayout.s3),
          child: _panel(snapshot),
        ),
      ),
    );
  }

  void _jumpToLocal(ChatTarget target) {
    if (target.conversationId != widget.conversation.id) return;
    setState(() {
      _followLatest = false;
      _lastTarget = target;
    });
    _jump.jumpTo(target);
  }

  void _scrollToLatest({bool force = false}) {
    if (!force && !_followLatest) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.jumpTo(_scroll.position.maxScrollExtent);
      if (force && mounted) setState(() => _followLatest = true);
    });
  }

  void _trackReadingPosition() {
    if (!_scroll.hasClients) return;
    final nearEnd =
        _scroll.position.maxScrollExtent - _scroll.position.pixels < 80;
    if (nearEnd != _followLatest && mounted) {
      setState(() => _followLatest = nearEnd);
    }
  }

  void _toggleBookmark(ChatTarget target) {
    final existing = widget.conversation.bookmarks
        .indexWhere((item) => item.target.messageId == target.messageId);
    var added = false;
    var changed = false;
    setState(() {
      if (existing >= 0) {
        widget.conversation.bookmarks.removeAt(existing);
        changed = true;
      } else {
        final index = _messageIndex(target.messageId);
        if (index < 0) return;
        final message = widget.conversation.messages[index];
        widget.conversation.bookmarks.add(ChatBookmark(
          target: target,
          label: _bookmarkTitle(message),
          createdAt: DateTime.now(),
        ));
        added = true;
        changed = true;
      }
      widget.conversation.touch();
    });
    if (!changed) return;
    widget.onConversationChanged();
    if (added) {
      _dispatchCue(RowanCompleteActionCueEvents.chatBookmarkAdded,
          _cueEventRef('bookmark_added', target: target));
    }
  }

  void _updateNotes(String value) {
    if (widget.conversation.notes == value) return;
    widget.conversation.notes = value;
    widget.conversation.touch();
    widget.onConversationChanged();
  }

  int _messageIndex(String messageId) => widget.conversation.messages
      .indexWhere((message) => message.id == messageId);

  String _bookmarkTitle(ChatMessage message) {
    final clean = message.text.trim().replaceAll('\n', ' ');
    if (clean.isEmpty) return message.isUser ? 'Empty prompt' : 'Empty answer';
    return clean.length <= 72 ? clean : '${clean.substring(0, 71)}…';
  }

  Future<void> _openUrl(String value) async {
    final uri = Uri.tryParse(value);
    if (uri == null || (uri.scheme != 'http' && uri.scheme != 'https')) return;
    await launchUrl(uri);
  }

  void _searchCommitted(String query) {
    if (query.trim().isEmpty) return;
    _dispatchCue(RowanCompleteActionCueEvents.chatHistorySearch,
        _cueEventRef('history_search', serial: ++_searchCommitSerial));
  }

  void _sourceJumped(ChatTarget target) {
    final resolved = resolveChatTarget(widget.conversation, target);
    if (resolved.precision == ChatTargetPrecision.missing) return;
    _dispatchCue(RowanCompleteActionCueEvents.chatJumpToSource,
        _cueEventRef('source_jump', target: target));
  }

  void _dispatchCue(RowanActionCueKind kind, String eventRef) {
    final controller = widget.actionCueController;
    if (controller == null) return;
    unawaited(controller.handle(
        RowanActionCueEvent.fromStableEvent(kind: kind, eventRef: eventRef)));
  }

  String _cueEventRef(String action, {ChatTarget? target, int? serial}) {
    final digest = rowanActionCueSha256({
      'action': action,
      'conversation_id': widget.conversation.id,
      'message_id': target?.messageId,
      'offset': target?.offset,
      'serial': serial,
    });
    return 'chat_${digest.substring(0, 32)}';
  }
}
