// chat_welcome.dart — the fresh-conversation welcome state with tappable
// starter chips so the user can begin with one tap instead of a cold blank.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'chat_composer.dart' show chatStarters;

class ChatWelcome extends StatelessWidget {
  final ValueChanged<String>? onStarter;
  const ChatWelcome({super.key, this.onStarter});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.auto_awesome_outlined, size: 30, color: t.verified),
          const SizedBox(height: FwLayout.s4),
          Text('What are we working on?',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: FwLayout.s2),
          Text(
            'Ask anything. Every answer runs on the model you pick and '
            'carries a receipt you can re-check.',
            textAlign: TextAlign.center,
            style: TextStyle(color: t.inkFaint, fontSize: 13.5, height: 1.5),
          ),
          if (onStarter != null) ...[
            const SizedBox(height: FwLayout.s5),
            Wrap(
              spacing: FwLayout.s2,
              runSpacing: FwLayout.s2,
              alignment: WrapAlignment.center,
              children: [
                for (final s in chatStarters)
                  ActionChip(
                    label: Text(s['title']!,
                        style: TextStyle(fontSize: 12.5, color: t.inkSoft)),
                    onPressed: () => onStarter!(s['text']!),
                    side: BorderSide(color: t.line),
                    backgroundColor: t.panel,
                    shape: RoundedRectangleBorder(
                        borderRadius:
                            BorderRadius.circular(FwLayout.radiusSmall)),
                  ),
              ],
            ),
          ],
        ]),
      ),
    );
  }
}
