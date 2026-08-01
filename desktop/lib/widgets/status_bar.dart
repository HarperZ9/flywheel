// status_bar.dart — the thin bottom status strip: gateway verdict, lane
// summary, an offline start action, and the world root hash. Kept minimal so
// the working surface stays the largest thing on screen.

import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class StatusBar extends StatelessWidget {
  final bool alive;
  final String message;
  final String? startError;
  final WorldDoc? world;
  final VoidCallback onStartEngine;
  const StatusBar({
    super.key,
    required this.alive,
    required this.message,
    required this.startError,
    required this.world,
    required this.onStartEngine,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: FwLayout.s3, vertical: 3),
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(top: BorderSide(color: t.line)),
      ),
      child: Row(
        children: [
          VerdictDot(alive ? 'live' : 'missing', size: 7),
          const SizedBox(width: FwLayout.s2),
          Text(message, style: fwMono(t, size: 11, color: t.inkMuted)),
          if (!alive) ...[
            const SizedBox(width: FwLayout.s3),
            MouseRegion(
              cursor: SystemMouseCursors.click,
              child: GestureDetector(
                onTap: onStartEngine,
                child: Text('start engine',
                    style: fwMono(t, size: 11, color: t.drift)
                        .copyWith(decoration: TextDecoration.underline)),
              ),
            ),
          ],
          if (startError != null) ...[
            const SizedBox(width: FwLayout.s3),
            Expanded(
              child: Text(startError!,
                  overflow: TextOverflow.ellipsis,
                  style: fwMono(t, size: 11, color: t.drift)),
            ),
          ] else
            const Spacer(),
          if (world != null && world!.rootHash.isNotEmpty) ...[
            HashText('world', world!.rootHash, keep: 16),
            const SizedBox(width: FwLayout.s4),
          ],
          Text('127.0.0.1:8799', style: fwMono(t, size: 11, color: t.inkFaint)),
        ],
      ),
    );
  }
}
