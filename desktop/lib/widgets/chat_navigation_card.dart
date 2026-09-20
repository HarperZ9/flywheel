import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'chat_navigation_types.dart';

class ChatNavigationCard extends StatelessWidget {
  final ChatNavigationItem item;
  final VoidCallback? onTap;
  final Widget? trailing;

  const ChatNavigationCard({
    super.key,
    required this.item,
    this.onTap,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final inset = ((item.level ?? 1) - 1).clamp(0, 5) * 10.0;
    return Padding(
      padding: EdgeInsets.only(left: inset, bottom: FwLayout.s2),
      child: Material(
        color: t.ground2,
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        child: InkWell(
          borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s3, vertical: FwLayout.s2),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
              border: Border.all(color: t.line),
            ),
            child: Row(children: [
              Icon(_icon(item.kind), size: 15, color: t.inkFaint),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(item.title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              fontWeight: FontWeight.w600,
                              color: t.ink,
                              height: 1.2)),
                      if (item.subtitle.isNotEmpty)
                        Text(item.subtitle,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: fwMono(t, size: 11.5, color: t.inkFaint)),
                    ]),
              ),
              if (trailing != null) trailing!,
            ]),
          ),
        ),
      ),
    );
  }
}

class ChatNavigationEmptyState extends StatelessWidget {
  final String text;
  const ChatNavigationEmptyState(this.text, {super.key});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(FwLayout.s5),
        child: Text(text,
            textAlign: TextAlign.center,
            style: TextStyle(color: context.fw.inkFaint, height: 1.4)),
      ),
    );
  }
}

IconData _icon(ChatNavigationKind kind) => switch (kind) {
      ChatNavigationKind.prompt => Icons.person_outline_rounded,
      ChatNavigationKind.heading => Icons.format_size_rounded,
      ChatNavigationKind.search => Icons.search_rounded,
      ChatNavigationKind.link => Icons.link_rounded,
      ChatNavigationKind.bookmark => Icons.bookmark_border_rounded,
    };
