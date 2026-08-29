import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

class CompanionInputBar extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onSend;
  const CompanionInputBar(
      {super.key, required this.controller, required this.onSend});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      padding: const EdgeInsets.fromLTRB(
          FwLayout.s5, FwLayout.s3, FwLayout.s5, FwLayout.s4),
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: t.hairline)),
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760),
        child: Container(
          decoration: BoxDecoration(
            color: t.panel,
            borderRadius: BorderRadius.circular(FwLayout.radius),
            border: Border.all(color: t.line),
          ),
          padding: const EdgeInsets.fromLTRB(FwLayout.s4, 4, 6, 6),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  maxLines: 4,
                  minLines: 1,
                  style: TextStyle(fontSize: 14, height: 1.45, color: t.ink),
                  decoration: InputDecoration(
                    isDense: true,
                    border: InputBorder.none,
                    hintText: 'Ask the companion…',
                    hintStyle: TextStyle(color: t.inkFaint, fontSize: 14),
                    contentPadding:
                        const EdgeInsets.symmetric(vertical: 10),
                  ),
                  onSubmitted: (_) => onSend(),
                ),
              ),
              const SizedBox(width: FwLayout.s2),
              IconButton.filled(
                onPressed: onSend,
                icon: const Icon(Icons.arrow_upward_rounded, size: 18),
                style: IconButton.styleFrom(
                  backgroundColor: t.ink,
                  foregroundColor: t.ground,
                ),
                tooltip: 'Send',
              ),
            ],
          ),
        ),
      ),
    );
  }
}
