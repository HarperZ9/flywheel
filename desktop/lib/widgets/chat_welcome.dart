// chat_welcome.dart — the fresh-conversation welcome frame.
//
// The current Chat destination supplies StartTaskPrelude as [child] so a new
// user starts with a plain task. The older starter-chip body stays available
// for focused Rowan identity tests and any caller that still wants it.

import 'package:flutter/material.dart';

import '../assistant/assistant_identity.dart';
import '../theme/flywheel_theme.dart';
import 'chat_composer.dart' show chatStarters;
import 'rowan_avatar.dart';

class ChatWelcome extends StatelessWidget {
  final ValueChanged<String>? onStarter;
  final Widget? child;
  const ChatWelcome({super.key, this.onStarter, this.child});

  @override
  Widget build(BuildContext context) {
    final body = child;
    if (body != null) return body;
    final t = context.fw;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const RowanAvatar(size: 64),
            const SizedBox(height: FwLayout.s4),
            Text(AssistantIdentity.welcome,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: FwLayout.s2),
            Text(
              AssistantIdentity.introduction,
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
      ),
    );
  }
}
