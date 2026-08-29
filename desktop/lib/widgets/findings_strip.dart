import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

/// One square per finding, verdict-tinted. A chart in the same hairline
/// language as everything else.
class FindingsStrip extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const FindingsStrip({super.key, required this.items});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Wrap(
      spacing: 3,
      runSpacing: 3,
      children: [
        for (final f in items)
          Container(
            width: 14,
            height: 14,
            decoration: BoxDecoration(
              color: (f['status'] == 'measured'
                      ? t.verified
                      : t.unverifiable)
                  .withValues(alpha: f['status'] == 'measured' ? 0.75 : 0.35),
              borderRadius: BorderRadius.circular(3),
              border: Border.all(color: t.line, width: 0.5),
            ),
          ),
      ],
    );
  }
}
