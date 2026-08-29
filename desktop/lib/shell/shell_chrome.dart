import 'package:flutter/material.dart';

import '../assistant/assistant_executor.dart';
import '../assistant/url_device_sink.dart';
import '../assistant/voice.dart';
import '../client/gateway_client.dart';
import '../models/recovery_item.dart';
import '../navigation/destination_catalog.dart';
import '../navigation/navigation_controller.dart';
import '../services/chat_draft_store.dart';
import '../services/journey_draft_store.dart';
import '../services/recovery_catalog.dart';
import '../services/recovery_sources.dart';
import '../theme/flywheel_theme.dart';
import '../views/recovery_center.dart';
import '../widgets/assistant_panel.dart';
import '../widgets/fw.dart';
import 'flywheel_dependencies.dart';
import 'gateway_status_coordinator.dart';

void openRecoveryCenter(
    BuildContext context, FlywheelDependencies deps) {
  final code = deps.code;
  showDialog<void>(
    context: context,
    builder: (dialogContext) => Dialog(
      insetPadding: const EdgeInsets.all(32),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 720),
        child: Scaffold(
          body: RecoveryCenter(
            catalog: RecoveryCatalog([
              ChatRecoverySource(ChatDraftStore()),
              CodeRecoverySource(code),
              JourneyRecoverySource(
                  JourneyDraftStore(),
                  acknowledgement: JourneyDraftAcknowledgement(
                      'recovery-center-'
                      '${DateTime.now().microsecondsSinceEpoch}',
                      'a' * 64)),
              InterruptedOperationRecoverySource(() => const []),
              IncompleteMigrationRecoverySource(),
              FailedUpdateRecoverySource(),
            ]),
          ),
        ),
      ),
    ),
  );
}

void openAssistant(BuildContext context, GatewayClient client,
    VoiceInput voiceInput, VoiceOutput voiceOutput) {
  showAssistantPanel(
    context,
    executor: AssistantExecutor(
      agent: GatewayAgentSink(client),
      device: UrlLauncherDeviceSink(),
    ),
    voiceInput: voiceInput,
    voiceOutput: voiceOutput,
  );
}

class ShellMobileTopBar extends StatelessWidget {
  const ShellMobileTopBar({
    super.key,
    required this.navigation,
    required this.coordinator,
    required this.onToggleTheme,
    required this.onAssistant,
  });

  final NavigationController navigation;
  final GatewayStatusCoordinator coordinator;
  final VoidCallback onToggleTheme;
  final VoidCallback onAssistant;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([coordinator, navigation]),
      builder: (context, _) {
        final t = context.fw;
        final spec = specFor(navigation.current.routeId);
        return Padding(
          padding: const EdgeInsets.fromLTRB(4, 6, 8, 2),
          child: Row(children: [
            IconButton(
              icon: Icon(Icons.menu, size: 20, color: t.inkMuted),
              tooltip: 'Open navigation',
              constraints:
                  const BoxConstraints(minWidth: 36, minHeight: 36),
              padding: const EdgeInsets.all(6),
              onPressed: () => Scaffold.of(context).openDrawer(),
            ),
            const SizedBox(width: 2),
            Text(spec?.label ?? 'Flywheel',
                style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: t.ink)),
            const SizedBox(width: 6),
            VerdictDot(
                coordinator.alive ? 'verified' : 'absent', size: 6),
            const Spacer(),
            _topAction(context, Icons.contrast, 'Theme',
                onToggleTheme),
            _topAction(context, Icons.assistant_rounded, 'Assistant',
                onAssistant),
          ]),
        );
      },
    );
  }

  Widget _topAction(
      BuildContext ctx, IconData icon, String tip, VoidCallback onTap) {
    return IconButton(
      icon: Icon(icon, size: 16, color: ctx.fw.inkMuted),
      tooltip: tip,
      constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
      padding: const EdgeInsets.all(4),
      onPressed: onTap,
    );
  }
}
