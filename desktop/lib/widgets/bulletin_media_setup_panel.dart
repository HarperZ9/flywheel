import 'package:flutter/material.dart';

import '../models/bulletin_media_models.dart';
import 'bulletin_media_artifact_row.dart';
import 'bulletin_media_credential_picker.dart';
import 'bulletin_media_run_row.dart';

final class BulletinMediaSetupPanel extends StatelessWidget {
  final bool busy;
  final TextEditingController runController;
  final TextEditingController credentialController;
  final TextEditingController destinationController;
  final TextEditingController roomController;
  final List<BulletinMediaRun> runs;
  final List<BulletinMediaArtifact> artifacts;
  final Set<String> selected;
  final Map<String, TextEditingController> altControllers;
  final VoidCallback onLoadRuns;
  final ValueChanged<BulletinMediaRun> onSelectRun;
  final VoidCallback onLoadArtifacts;
  final void Function(BulletinMediaArtifact artifact, bool? value)
      onArtifactChanged;

  const BulletinMediaSetupPanel({
    super.key,
    required this.busy,
    required this.runController,
    required this.credentialController,
    required this.destinationController,
    required this.roomController,
    required this.runs,
    required this.artifacts,
    required this.selected,
    required this.altControllers,
    required this.onLoadRuns,
    required this.onSelectRun,
    required this.onLoadArtifacts,
    required this.onArtifactChanged,
  });

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          FilledButton(
              key: const ValueKey('bulletin-load-runs'),
              onPressed: busy ? null : onLoadRuns,
              child: const Text('Load runs')),
          const SizedBox(height: 8),
          ...runs.map((run) => BulletinMediaRunRow(
                run: run,
                selected: runController.text.trim() == run.runId,
                onTap: () => onSelectRun(run),
              )),
          bulletinMediaField(runController, 'Run id', 'bulletin-run-id'),
          BulletinMediaCredentialPicker(
              controller: credentialController, busy: busy),
          bulletinMediaField(destinationController, 'Bulletin destination',
              'bulletin-destination'),
          bulletinMediaField(roomController, 'Room', 'bulletin-room'),
          FilledButton(
              key: const ValueKey('bulletin-load-artifacts'),
              onPressed: busy ? null : onLoadArtifacts,
              child: const Text('Load artifacts')),
          const SizedBox(height: 12),
          ...artifacts.map((artifact) => BulletinMediaArtifactRow(
                artifact: artifact,
                selected: selected.contains(artifact.artifactId),
                altController: altControllers.putIfAbsent(
                    artifact.artifactId, TextEditingController.new),
                onChanged: (value) => onArtifactChanged(artifact, value),
              )),
        ],
      );
}
