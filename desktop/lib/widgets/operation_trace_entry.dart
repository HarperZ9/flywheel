import 'package:flutter/material.dart';
import '../client/gateway_client.dart';
import '../models/agent_trace.dart';
import '../models/operation_models.dart';
import 'agent_trace_viewer.dart';

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
    Map<String, dynamic>? raw;
    if (result != null && result!.result['schema'] == traceProjectionSchema) {
      if (result!.operationRef != snapshot.operationRef ||
          result!.state != snapshot.state ||
          result!.canonicalSha256 != snapshot.resultSha256) {
        return const Text(
            'Private trace unavailable: operation result did not match.');
      }
      raw = Map<String, dynamic>.from(result!.result);
    } else if (!snapshot.isTerminal) {
      for (final event in progress.reversed) {
        if (event['schema'] == traceProjectionSchema) {
          raw = event;
          break;
        }
      }
    }
    if (raw == null) return const SizedBox.shrink();
    try {
      final projection = TraceProjection.fromJson(raw,
          operationRef: snapshot.operationRef, journeyRef: snapshot.journeyRef);
      if ((snapshot.isTerminal && projection.state != result?.state.name) ||
          (!snapshot.isTerminal && !projection.isRunning)) {
        invalidTrace();
      }
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
    } catch (_) {
      return const Text('Private trace unavailable: metadata did not match.');
    }
  }
}
