// open_panel.dart — the Code view's landing state: open a project folder by
// path, or pick a recent workspace. Kept apart so the view stays a composer.

import 'package:flutter/material.dart';

import '../services/settings.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class OpenWorkspacePanel extends StatefulWidget {
  final DesktopSettings settings;
  final ValueChanged<String> onOpen;
  final String? status;
  const OpenWorkspacePanel(
      {super.key, required this.settings, required this.onOpen, this.status});

  @override
  State<OpenWorkspacePanel> createState() => _OpenWorkspacePanelState();
}

class _OpenWorkspacePanelState extends State<OpenWorkspacePanel> {
  final _pathInput = TextEditingController();

  @override
  void dispose() {
    _pathInput.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SectionHeader('Code', kicker: 'the workspace lane'),
            const SizedBox(height: FwLayout.s3),
            Text(
              'Open a folder to edit it here. The workspace agent runs the '
              'same gated, witnessed loop over your project, on any endpoint.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: FwLayout.s4),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _pathInput,
                    style: fwMono(t, size: 12.5),
                    decoration: const InputDecoration(
                        hintText: 'Path to a project folder…'),
                    onSubmitted: widget.onOpen,
                  ),
                ),
                const SizedBox(width: FwLayout.s3),
                FilledButton(
                  onPressed: () => widget.onOpen(_pathInput.text),
                  child: const Text('Open'),
                ),
              ],
            ),
            if (widget.status != null) ...[
              const SizedBox(height: FwLayout.s3),
              HonestNull(widget.status!),
            ],
            if (widget.settings.recentWorkspaces.isNotEmpty) ...[
              const SizedBox(height: FwLayout.s5),
              const Kicker('recent'),
              const SizedBox(height: FwLayout.s2),
              for (final r in widget.settings.recentWorkspaces)
                MouseRegion(
                  cursor: SystemMouseCursors.click,
                  child: GestureDetector(
                    onTap: () => widget.onOpen(r),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Text(r,
                          overflow: TextOverflow.ellipsis,
                          style: fwMono(t, size: 12, color: t.drift)),
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
