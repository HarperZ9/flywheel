import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

enum ChatNavigationSection { outline, search, links, bookmarks, notes }

class ChatNavigationSectionButton extends StatelessWidget {
  final ChatNavigationSection section;
  final bool selected;
  final VoidCallback onPressed;

  const ChatNavigationSectionButton({
    super.key,
    required this.section,
    required this.selected,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Semantics(
      button: true,
      selected: selected,
      child: TextButton(
        onPressed: onPressed,
        style: TextButton.styleFrom(
          backgroundColor: selected ? t.ink : Colors.transparent,
          foregroundColor: selected ? t.ground : t.inkFaint,
          minimumSize: const Size(44, 44),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          tapTargetSize: MaterialTapTargetSize.padded,
          side: BorderSide(color: selected ? t.ink : t.hairline),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(9)),
        ),
        child: Text(section.label),
      ),
    );
  }
}

extension ChatNavigationSectionLabel on ChatNavigationSection {
  String get label => switch (this) {
        ChatNavigationSection.outline => 'Outline',
        ChatNavigationSection.search => 'Search',
        ChatNavigationSection.links => 'Links',
        ChatNavigationSection.bookmarks => 'Bookmarks',
        ChatNavigationSection.notes => 'Notes',
      };
}
