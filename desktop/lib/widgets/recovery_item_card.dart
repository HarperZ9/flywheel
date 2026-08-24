// recovery_item_card.dart -- one recoverable item: kind chip, title,
// detail, and its advertised actions. Actions the item does not advertise
// never render, so an invalid action is unreachable, not merely refused.
import 'package:flutter/material.dart';

import '../accessibility/accessible_action.dart';
import '../models/recovery_item.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

String recoveryKindLabel(RecoveryKind kind) => switch (kind) {
      RecoveryKind.unsentChat => 'unsent prompt',
      RecoveryKind.dirtyCode => 'dirty buffer',
      RecoveryKind.pendingJourney => 'journey draft',
      RecoveryKind.interruptedOperation => 'interrupted operation',
      RecoveryKind.incompleteMigration => 'incomplete migration',
      RecoveryKind.failedUpdate => 'failed update',
    };

class RecoveryItemCard extends StatelessWidget {
  final RecoveryItem item;
  final ValueChanged<RecoveryActionSpec> onAction;
  const RecoveryItemCard(
      {super.key, required this.item, required this.onAction});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s3),
      child: HairlineCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              VerdictPill(recoveryKindLabel(item.kind),
                  status: 'unverifiable'),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: Text(item.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 13, color: t.ink)),
              ),
            ]),
            const SizedBox(height: FwLayout.s2),
            Text(item.detail,
                style: TextStyle(fontSize: 11.5, color: t.inkMuted)),
            const SizedBox(height: FwLayout.s3),
            Wrap(
              spacing: FwLayout.s2,
              children: [
                for (final action in item.actions)
                  AccessibleAction(
                    semanticLabel:
                        '${action.label}: ${recoveryKindLabel(item.kind)}',
                    onActivate: () => onAction(action),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(
                            FwLayout.radiusSmall),
                        border: Border.all(
                            color: action.destructive
                                ? t.drift.withValues(alpha: 0.5)
                                : t.line),
                      ),
                      child: Text(action.label,
                          style: TextStyle(
                              fontSize: 12,
                              color: action.destructive
                                  ? t.drift
                                  : t.inkMuted)),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
