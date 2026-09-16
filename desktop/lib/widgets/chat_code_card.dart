import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/flywheel_theme.dart';

class ChatCodeCard extends StatelessWidget {
  final String code;
  const ChatCodeCard({super.key, required this.code});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(vertical: 6),
      decoration: BoxDecoration(
        color: t.ground2,
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        border: Border.all(color: t.hairline),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Align(
          alignment: Alignment.centerRight,
          child: IconButton(
            onPressed: () => Clipboard.setData(ClipboardData(text: code)),
            icon: const Icon(Icons.copy_rounded, size: 13),
            visualDensity: VisualDensity.compact,
            color: t.inkFaint,
            tooltip: 'Copy code',
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(
              FwLayout.s3, 0, FwLayout.s3, FwLayout.s3),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SelectableText(code,
                style: fwMono(t, size: 12.5, color: t.ink)),
          ),
        ),
      ]),
    );
  }
}
