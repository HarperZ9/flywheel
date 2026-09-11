import 'package:flutter/material.dart';
import '../client/gateway_client.dart';
import '../models/operation_models.dart';
import 'agent_trace_viewer.dart';
import 'operation_trace_projection.dart';

/// Public projection metadata is only a locator for an explicit private read.
class OperationTraceEntry extends StatelessWidget {
  final GatewayClient client;
  final OperationSnapshot snapshot;
  final OperationResult? result;
  final List<Map<String, dynamic>> progress;
  const OperationTraceEntry(
      {super.key,
      required this.client,
      required this.snapshot,
      this.result,
      required this.progress});

  @override
  Widget build(BuildContext context) {
    try {
      final projection = acceptedOperationTraceProjection(
          snapshot: snapshot, result: result, progress: progress);
      if (projection == null) return const SizedBox.shrink();
      return TextButton.icon(
        icon: const Icon(Icons.receipt_long_outlined, size: 16),
        label: Text(
            'Private trace · ${projection.state} · ${projection.recordCount} records'),
        onPressed: () {
          final reader = GatewayAgentTrace(client);
          showDialog<void>(
              context: context,
              builder: (context) => Dialog(
                  child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 850),
                      child: Padding(
                          padding: const EdgeInsets.all(16),
                          child:
                              Column(mainAxisSize: MainAxisSize.min, children: [
                            Flexible(
                                child: SingleChildScrollView(
                                    child: AgentTraceViewer(
                                        projection: projection,
                                        reader: reader))),
                            TextButton(
                                onPressed: () => Navigator.of(context).pop(),
                                child: const Text('Close private trace')),
                          ])))));
        },
      );
    } on OperationTraceProjectionException catch (error) {
      return Text(error.message);
    }
  }
}
