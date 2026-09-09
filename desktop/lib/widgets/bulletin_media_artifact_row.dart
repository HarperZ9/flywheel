import 'package:flutter/material.dart';

import '../models/bulletin_media_models.dart';

final class BulletinMediaArtifactRow extends StatelessWidget {
  final BulletinMediaArtifact artifact;
  final bool selected;
  final TextEditingController altController;
  final ValueChanged<bool?> onChanged;

  const BulletinMediaArtifactRow({
    super.key,
    required this.artifact,
    required this.selected,
    required this.altController,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) => Card(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          CheckboxListTile(
            key: ValueKey('bulletin-artifact-${artifact.artifactId}'),
            value: selected,
            onChanged: onChanged,
            title: Text('${artifact.label} · ${artifact.kind.name}'),
            subtitle: Text('${artifact.mediaType} · ${artifact.bytes} bytes'),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: TextField(
              key: ValueKey('bulletin-alt-${artifact.artifactId}'),
              controller: altController,
              decoration:
                  const InputDecoration(labelText: 'Alt or listening context'),
            ),
          ),
        ]),
      );
}

Widget bulletinMediaField(
        TextEditingController controller, String label, String key) =>
    TextField(
      key: ValueKey(key),
      controller: controller,
      decoration: InputDecoration(labelText: label),
    );

Widget bulletinMediaMultiline(
        TextEditingController controller, String label, String key) =>
    TextField(
      key: ValueKey(key),
      controller: controller,
      maxLines: 3,
      decoration: InputDecoration(labelText: label),
    );
