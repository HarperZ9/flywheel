// chat_welcome.dart — the fresh-conversation welcome state, split from
// AgentView to hold the size gate.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

class ChatWelcome extends StatelessWidget {
  const ChatWelcome({super.key});

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
            'Ask anything. Every answer runs on the model you pick and carries a '
            'receipt you can re-check. The trust is built in, never in the way.',
            textAlign: TextAlign.center,
            style: TextStyle(color: t.inkFaint, fontSize: 13.5, height: 1.5),
          ),
        ]),
      ),
    );
  }
}
