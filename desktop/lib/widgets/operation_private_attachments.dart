import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/operation_models.dart';
import 'operation_caption_entry.dart';
import 'operation_trace_entry.dart';

class OperationPrivateAttachments extends StatelessWidget {
  final GatewayClient client;
  final OperationSnapshot snapshot;
  final OperationResult? result;
  final List<Map<String, dynamic>> progress;
  const OperationPrivateAttachments({
    super.key,
    required this.client,
    required this.snapshot,
    this.result,
    required this.progress,
  });

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          OperationTraceEntry(
            client: client,
            snapshot: snapshot,
            result: result,
            progress: progress,
          ),
          OperationCaptionEntry(
            client: client,
            snapshot: snapshot,
            result: result,
            progress: progress,
          ),
        ],
      );
}
