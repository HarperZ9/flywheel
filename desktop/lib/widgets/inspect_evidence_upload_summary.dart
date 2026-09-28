import 'package:flutter/material.dart';

import '../models/inspect_evidence_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class InspectEvidenceUploadSummary extends StatelessWidget {
  final InspectEvidenceUpload upload;
  const InspectEvidenceUploadSummary({super.key, required this.upload});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final unit = upload.unitContract;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s2, children: [
        HashText('source', upload.sha256, keep: 24),
        Text('${upload.byteLength} bytes',
            style: fwMono(t, size: 11.5, color: t.inkMuted)),
        if (upload.filename != null)
          Text(upload.filename!,
              style: fwMono(t, size: 11.5, color: t.inkMuted)),
      ]),
      const SizedBox(height: FwLayout.s2),
      Text(upload.dataRef, style: fwMono(t, size: 11, color: t.inkFaint)),
      if (unit != null) ...[
        const SizedBox(height: FwLayout.s2),
        Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s2, children: [
          HashText('unit sidecar', unit.sha256, keep: 24),
          Text('${unit.byteLength} bytes',
              style: fwMono(t, size: 11.5, color: t.inkMuted)),
          if (unit.filename != null)
            Text(unit.filename!,
                style: fwMono(t, size: 11.5, color: t.inkMuted)),
        ]),
      ],
    ]);
  }
}
