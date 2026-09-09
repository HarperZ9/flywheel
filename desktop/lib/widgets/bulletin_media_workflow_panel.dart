import 'package:flutter/material.dart';

import '../models/bulletin_media_models.dart';
import '../services/bulletin_media_cache.dart';
import 'bulletin_media_artifact_row.dart';
import 'bulletin_media_review_panel.dart';
import 'bulletin_media_setup_panel.dart';

final class BulletinMediaWorkflowPanel extends StatelessWidget {
  final bool busy;
  final TextEditingController runController;
  final TextEditingController credentialController;
  final TextEditingController destinationController;
  final TextEditingController roomController;
  final TextEditingController titleController;
  final TextEditingController descriptionController;
  final TextEditingController sourceController;
  final List<BulletinMediaRun> runs;
  final List<BulletinMediaArtifact> artifacts;
  final Set<String> selected;
  final Map<String, TextEditingController> altControllers;
  final BulletinMediaPreviewResponse? preview;
  final BulletinMediaPublishResult? result;
  final String? message;
  final BulletinMediaLoader loader;
  final VoidCallback onLoadRuns;
  final ValueChanged<BulletinMediaRun> onSelectRun;
  final VoidCallback onLoadArtifacts;
  final VoidCallback onPreview;
  final VoidCallback onPublish;
  final void Function(BulletinMediaArtifact artifact, bool? value)
      onArtifactChanged;

  const BulletinMediaWorkflowPanel({
    super.key,
    required this.busy,
    required this.runController,
    required this.credentialController,
    required this.destinationController,
    required this.roomController,
    required this.titleController,
    required this.descriptionController,
    required this.sourceController,
    required this.runs,
    required this.artifacts,
    required this.selected,
    required this.altControllers,
    required this.preview,
    required this.result,
    required this.message,
    required this.loader,
    required this.onLoadRuns,
    required this.onSelectRun,
    required this.onLoadArtifacts,
    required this.onPreview,
    required this.onPublish,
    required this.onArtifactChanged,
  });

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Bulletin', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 12),
          BulletinMediaSetupPanel(
            busy: busy,
            runController: runController,
            credentialController: credentialController,
            destinationController: destinationController,
            roomController: roomController,
            runs: runs,
            artifacts: artifacts,
            selected: selected,
            altControllers: altControllers,
            onLoadRuns: onLoadRuns,
            onSelectRun: onSelectRun,
            onLoadArtifacts: onLoadArtifacts,
            onArtifactChanged: onArtifactChanged,
          ),
          const Divider(height: 24),
          bulletinMediaField(titleController, 'Public title', 'bulletin-title'),
          bulletinMediaMultiline(
              descriptionController, 'Public body', 'bulletin-body'),
          bulletinMediaMultiline(
              sourceController, 'Source/context', 'bulletin-source'),
          const SizedBox(height: 12),
          FilledButton(
              key: const ValueKey('bulletin-preview'),
              onPressed: busy ? null : onPreview,
              child: const Text('Preview selected media')),
          if (message != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(message!),
            ),
          if (preview != null) ...[
            const SizedBox(height: 16),
            BulletinMediaReviewPanel(review: preview!.review, loader: loader),
            const SizedBox(height: 12),
            FilledButton(
                key: const ValueKey('bulletin-publish'),
                onPressed: busy ? null : onPublish,
                child: const Text('Approve and publish')),
          ],
          if (result != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(result!.humanStatus),
            ),
        ]),
      );
}
