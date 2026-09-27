// chat_history_banner.dart: what chat history could not do, said where the
// history lives (design 7.9). Files set aside as unreadable, archive segments
// that were skipped, a paused save, a conversation too large to keep, a
// delete that did not finish, and the archived conversations, which open
// read-only on demand. Every notice names what was kept; nothing here
// deletes without a second confirmation.

import 'dart:io';

import 'package:flutter/material.dart';

import '../models/chat.dart';
import '../services/chat_store.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ChatHistoryBanner extends StatelessWidget {
  const ChatHistoryBanner(
      {super.key, required this.store, required this.onDeleteArchived});

  final ChatStore store;

  /// Deletes an archived conversation by id through the same path the
  /// conversation list uses, so drafts and every file are covered.
  final ValueChanged<String> onDeleteArchived;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: store.status,
      builder: (context, _) {
        final status = store.status;
        final notes = <Widget>[
          for (final path in status.setAside)
            _SetAside(store: store, path: path),
          for (final path in status.skippedSegments)
            HonestNull('An archived history file could not be read and was '
                'skipped: $path. Nothing was deleted.'),
          if (status.savingPaused)
            const HonestNull('Chat history could not be read, so saving is '
                'paused and the file is not replaced.'),
          if (status.oversizeConversation != null)
            const HonestNull('A conversation is too large for history (over 1 MiB '
                'or 4096 JSON nodes). Its last saved copy is kept and its latest turn '
                'stays in drafts; other conversations still save.'),
          if (status.deleteIncomplete)
            const HonestNull('A delete did not reach every history file. '
                'The conversation may appear again when history reloads.'),
          if (status.archivedCount > 0)
            _Archived(store: store, onDelete: onDeleteArchived),
        ];
        if (notes.isEmpty) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.fromLTRB(
              FwLayout.s3, 0, FwLayout.s3, FwLayout.s2),
          child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final note in notes)
                  Padding(
                      padding: const EdgeInsets.only(bottom: FwLayout.s2),
                      child: note),
              ]),
        );
      });
}

class _SetAside extends StatelessWidget {
  const _SetAside({required this.store, required this.path});
  final ChatStore store;
  final String path;

  @override
  Widget build(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        HonestNull('Chat history could not be read and was set aside at '
            '$path. Nothing was deleted.'),
        TextButton(
            onPressed: () async {
              if (await _confirm(context, 'Delete the set-aside file?',
                  'The app could not parse it. Open it in a text editor '
                  'first if you want anything from it. Deleting removes the '
                  'whole file at $path.')) {
                store.removeQuarantined(File(path));
              }
            },
            child: const Text('Delete this file')),
      ]);
}

class _Archived extends StatelessWidget {
  const _Archived({required this.store, required this.onDelete});
  final ChatStore store;
  final ValueChanged<String> onDelete;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final count = store.status.archivedCount;
    return Row(children: [
      Expanded(
          child: Text(
              '$count archived conversation${count == 1 ? '' : 's'}',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted))),
      TextButton(
          onPressed: () => _showArchive(context, store, onDelete),
          child: const Text('Show')),
    ]);
  }
}

Future<void> _showArchive(BuildContext context, ChatStore store,
        ValueChanged<String> onDelete) =>
    showDialog<void>(
      context: context,
      builder: (dialogContext) {
        final archived = store.loadArchived();
        return AlertDialog(
          title: const Text('Archived conversations'),
          content: SizedBox(
            width: 420,
            height: 360,
            child: ListView(children: [
              for (final conversation in archived)
                ListTile(
                  title: Text(conversation.title,
                      maxLines: 1, overflow: TextOverflow.ellipsis),
                  subtitle: const Text('Read-only'),
                  onTap: () => _showReadOnly(dialogContext, conversation,
                      () {
                    onDelete(conversation.id);
                    Navigator.of(dialogContext).pop();
                  }),
                ),
            ]),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text('Close')),
          ],
        );
      },
    );

Future<void> _showReadOnly(BuildContext context, Conversation conversation,
        VoidCallback onDelete) =>
    showDialog<void>(
      context: context,
      builder: (readerContext) => AlertDialog(
        title: Text(conversation.title),
        content: SizedBox(
          width: 520,
          height: 420,
          child: ListView(children: [
            for (final message in conversation.messages)
              Padding(
                padding: const EdgeInsets.only(bottom: FwLayout.s3),
                child: SelectableText(
                    '${message.isUser ? 'You' : 'Assistant'}: ${message.text}'),
              ),
          ]),
        ),
        actions: [
          TextButton(
              onPressed: () async {
                if (await confirmConversationDelete(readerContext)) {
                  onDelete();
                  if (readerContext.mounted) Navigator.of(readerContext).pop();
                }
              },
              child: const Text('Delete')),
          TextButton(
              onPressed: () => Navigator.of(readerContext).pop(),
              child: const Text('Close')),
        ],
      ),
    );

/// The one confirmation every conversation delete shows, from the list or
/// from the archive reader: what is removed, that there is no undo, and what
/// is not reached.
Future<bool> confirmConversationDelete(BuildContext context) => _confirm(
    context,
    'Delete this conversation?',
    'It is removed from the archive, the active history and the drafts, '
    'and there is no undo. Old bytes in freed disk space, the gateway '
    'traces of these turns and the model provider\'s copy are not reached.');

Future<bool> _confirm(BuildContext context, String title, String body) async =>
    await showDialog<bool>(
      context: context,
      builder: (confirmContext) => AlertDialog(
        title: Text(title),
        content: Text(body),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(confirmContext).pop(false),
              child: const Text('Keep')),
          TextButton(
              onPressed: () => Navigator.of(confirmContext).pop(true),
              child: const Text('Delete')),
        ],
      ),
    ) ??
    false;
