import 'package:flutter/material.dart';
import 'chat_navigation_card.dart';
import 'chat_navigation_sections.dart';
import 'chat_navigation_types.dart';
import 'fw.dart';

class ChatNavigationPanel extends StatefulWidget {
  final ChatNavigationSnapshot snapshot;
  final String conversationId;
  final String notes;
  final String? sourceReference;
  final ValueChanged<String> onNotesChanged;
  final ValueChanged<ChatNavTarget> onTargetSelected;
  final ValueChanged<String> onOpenUrl;
  final ValueChanged<String>? onSearchCommitted;
  final ValueChanged<ChatNavTarget>? onSourceJump;
  const ChatNavigationPanel({
    super.key,
    required this.snapshot,
    required this.conversationId,
    required this.notes,
    this.sourceReference,
    required this.onNotesChanged,
    required this.onTargetSelected,
    required this.onOpenUrl,
    this.onSearchCommitted,
    this.onSourceJump,
  });
  @override
  State<ChatNavigationPanel> createState() => _ChatNavigationPanelState();
}

class _ChatNavigationPanelState extends State<ChatNavigationPanel> {
  final _search = TextEditingController();
  final _notes = TextEditingController();
  ChatNavigationSection _section = ChatNavigationSection.outline;
  @override
  void initState() {
    super.initState();
    _notes.text = widget.notes;
  }

  @override
  void didUpdateWidget(ChatNavigationPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.notes != widget.notes && _notes.text != widget.notes) {
      _notes.text = widget.notes;
    }
  }

  @override
  void dispose() {
    _search.dispose();
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return HairlineCard(
      padding: EdgeInsets.zero,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(
              FwLayout.s4, FwLayout.s4, FwLayout.s4, FwLayout.s2),
          child: Kicker('Navigate'),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(
              FwLayout.s3, 0, FwLayout.s3, FwLayout.s2),
          child: Semantics(
            label: 'Chat navigation sections',
            child: Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final section in ChatNavigationSection.values)
                  ChatNavigationSectionButton(
                    section: section,
                    selected: _section == section,
                    onPressed: () => setState(() => _section = section),
                  ),
              ],
            ),
          ),
        ),
        Expanded(
          child: switch (_section) {
            ChatNavigationSection.outline => _ItemList(
                items: widget.snapshot.outline,
                empty: 'No prompts or Markdown headings yet.',
                onTargetSelected: widget.onTargetSelected,
              ),
            ChatNavigationSection.search => _SearchTab(
                controller: _search,
                search: widget.snapshot.search,
                onTargetSelected: widget.onTargetSelected,
                onSearchCommitted: widget.onSearchCommitted,
              ),
            ChatNavigationSection.links => _LinksTab(
                items: widget.snapshot.links,
                onTargetSelected: widget.onTargetSelected,
                onOpenUrl: widget.onOpenUrl,
                onSourceJump: widget.onSourceJump,
              ),
            ChatNavigationSection.bookmarks => _ItemList(
                items: widget.snapshot.bookmarks,
                empty:
                    'No bookmarks yet. Use the bookmark control on any turn.',
                onTargetSelected: widget.onTargetSelected,
              ),
            ChatNavigationSection.notes => _NotesTab(
                controller: _notes,
                sourceReference: widget.sourceReference,
                onChanged: widget.onNotesChanged,
              ),
          },
        ),
      ]),
    );
  }
}

class _SearchTab extends StatelessWidget {
  final TextEditingController controller;
  final ChatNavigationSearch search;
  final ValueChanged<ChatNavTarget> onTargetSelected;
  final ValueChanged<String>? onSearchCommitted;
  const _SearchTab({
    required this.controller,
    required this.search,
    required this.onTargetSelected,
    this.onSearchCommitted,
  });
  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final hits = search(controller.text);
        return Padding(
          padding: const EdgeInsets.all(FwLayout.s3),
          child: Column(children: [
            TextField(
              key: const ValueKey('chat-nav-search'),
              controller: controller,
              textInputAction: TextInputAction.search,
              onSubmitted: _commit,
              decoration: const InputDecoration(
                hintText: 'Find exact text in this chat',
                prefixIcon: Icon(Icons.search_rounded),
              ),
            ),
            const SizedBox(height: FwLayout.s3),
            Expanded(
              child: _ItemList(
                items: hits,
                empty: controller.text.trim().isEmpty
                    ? 'Search stays local to the saved conversation.'
                    : 'No matches.',
                onTargetSelected: onTargetSelected,
              ),
            ),
          ]),
        );
      },
    );
  }

  void _commit(String value) {
    final query = value.trim();
    if (query.isNotEmpty) onSearchCommitted?.call(query);
  }
}

class _LinksTab extends StatelessWidget {
  final List<ChatNavigationItem> items;
  final ValueChanged<ChatNavTarget> onTargetSelected;
  final ValueChanged<String> onOpenUrl;
  final ValueChanged<ChatNavTarget>? onSourceJump;
  const _LinksTab({
    required this.items,
    required this.onTargetSelected,
    required this.onOpenUrl,
    this.onSourceJump,
  });
  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const ChatNavigationEmptyState('No HTTP(S) links found yet.');
    }
    return ListView.builder(
      padding: const EdgeInsets.all(FwLayout.s3),
      itemCount: items.length,
      itemBuilder: (context, index) {
        final item = items[index];
        final url = item.url ?? item.subtitle;
        return ChatNavigationCard(
          item: item,
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            IconButton(
              tooltip: 'Jump to source for ${item.title}',
              onPressed: () => _jumpToSource(item.target),
              icon: const Icon(Icons.my_location_rounded, size: 16),
            ),
            IconButton(
              tooltip: 'Open ${item.title}',
              onPressed: () => onOpenUrl(url),
              icon: const Icon(Icons.open_in_new_rounded, size: 16),
            ),
          ]),
        );
      },
    );
  }

  void _jumpToSource(ChatNavTarget target) {
    onTargetSelected(target);
    onSourceJump?.call(target);
  }
}

class _ItemList extends StatelessWidget {
  final List<ChatNavigationItem> items;
  final String empty;
  final ValueChanged<ChatNavTarget> onTargetSelected;
  const _ItemList({
    required this.items,
    required this.empty,
    required this.onTargetSelected,
  });
  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return ChatNavigationEmptyState(empty);
    return ListView.builder(
      padding: const EdgeInsets.all(FwLayout.s3),
      itemCount: items.length,
      itemBuilder: (context, index) => ChatNavigationCard(
        item: items[index],
        onTap: () => onTargetSelected(items[index].target),
      ),
    );
  }
}

class _NotesTab extends StatelessWidget {
  final TextEditingController controller;
  final String? sourceReference;
  final ValueChanged<String> onChanged;
  const _NotesTab({
    required this.controller,
    required this.sourceReference,
    required this.onChanged,
  });
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(FwLayout.s3),
      child: Column(children: [
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: sourceReference == null ? null : _insertSource,
            icon: const Icon(Icons.add_link_rounded, size: 16),
            label: const Text('Insert source link'),
          ),
        ),
        const SizedBox(height: FwLayout.s2),
        Expanded(
          child: TextField(
            key: const ValueKey('chat-nav-notes'),
            controller: controller,
            expands: true,
            maxLines: null,
            minLines: null,
            onChanged: onChanged,
            textAlignVertical: TextAlignVertical.top,
            decoration: const InputDecoration(
              hintText:
                  'Working notes and source backlinks for this conversation',
            ),
          ),
        ),
      ]),
    );
  }

  void _insertSource() {
    final reference = sourceReference;
    if (reference == null) return;
    final text = controller.text.trimRight();
    final next = text.isEmpty ? reference : '$text\n$reference';
    controller.text = next;
    controller.selection = TextSelection.collapsed(offset: next.length);
    onChanged(next);
  }
}
