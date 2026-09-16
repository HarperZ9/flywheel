import 'package:flutter/material.dart';

import '../controllers/chat_context_controller.dart';
import '../theme/flywheel_theme.dart';

class ChatContextStatus extends StatelessWidget {
  const ChatContextStatus({super.key, required this.outcome});

  final ChatContextOutcome? outcome;

  @override
  Widget build(BuildContext context) {
    final text = outcome?.displayText ?? '';
    if (text.isEmpty) return const SizedBox.shrink();
    final t = context.fw;
    return Container(
      alignment: Alignment.center,
      padding: const EdgeInsets.fromLTRB(
          FwLayout.s5, FwLayout.s2, FwLayout.s5, FwLayout.s2),
      decoration: BoxDecoration(
          color: t.ground2, border: Border(top: BorderSide(color: t.hairline))),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760),
        child: Row(children: [
          Icon(Icons.history_edu_rounded, size: 15, color: t.inkFaint),
          const SizedBox(width: FwLayout.s2),
          Expanded(
              child: Text(text,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      color: t.inkSoft, fontSize: 12.5, height: 1.35))),
        ]),
      ),
    );
  }
}
