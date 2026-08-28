import 'dart:io' show Platform;

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

/// Empty / offline state. States the fact plainly and shows the command
/// that changes it. No decoration.
class FwEmpty extends StatelessWidget {
  final String message;
  final String? command;

  /// Whether this is a phone. A phone has no terminal and reaches a paired
  /// engine over the network, so it points at where the engine lives instead
  /// of a shell command it cannot run. Null resolves to the real platform;
  /// tests pass an explicit value to exercise both branches. Resolution uses
  /// dart:io Platform, not defaultTargetPlatform, because the latter reads as
  /// android under flutter test and would flip the desktop branch.
  final bool? mobile;
  const FwEmpty(this.message, {super.key, this.command, this.mobile});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final onPhone = mobile ?? (Platform.isAndroid || Platform.isIOS);
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(message,
              style: TextStyle(color: t.inkMuted, fontSize: 13.5),
              textAlign: TextAlign.center),
          if (command != null) ...[
            const SizedBox(height: FwLayout.s3),
            if (onPhone)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: FwLayout.s4),
                child: Text('The engine runs on your computer. Pair it from Connection.',
                    style: TextStyle(color: t.inkFaint, fontSize: 12.5),
                    textAlign: TextAlign.center),
              )
            else
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: FwLayout.s3, vertical: FwLayout.s2),
                decoration: BoxDecoration(
                  color: t.ground2,
                  borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
                  border: Border.all(color: t.line),
                ),
                child: SelectableText(command!, style: fwMono(t, size: 12.5)),
              ),
          ],
        ],
      ),
    );
  }
}
