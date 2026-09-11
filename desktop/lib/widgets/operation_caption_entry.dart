import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/operation_models.dart';
import 'agent_caption_panel.dart';
import 'operation_trace_projection.dart';

class OperationCaptionEntry extends StatefulWidget {
  final GatewayClient client;
  final OperationSnapshot snapshot;
  final OperationResult? result;
  final List<Map<String, dynamic>> progress;
  const OperationCaptionEntry({
    super.key,
    required this.client,
    required this.snapshot,
    this.result,
    required this.progress,
  });

  @override
  State<OperationCaptionEntry> createState() => _OperationCaptionEntryState();
}

class _OperationCaptionEntryState extends State<OperationCaptionEntry> {
  late GatewayAgentTrace _reader;

  @override
  void initState() {
    super.initState();
    _reader = GatewayAgentTrace(widget.client);
  }

  @override
  void didUpdateWidget(covariant OperationCaptionEntry oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.client != widget.client) {
      _reader = GatewayAgentTrace(widget.client);
    }
  }

  @override
  Widget build(BuildContext context) {
    final projection = _projection();
    if (projection == null) return const SizedBox.shrink();
    return AgentCaptionPanel(reader: _reader, projection: projection);
  }

  dynamic _projection() {
    try {
      return acceptedOperationTraceProjection(
        snapshot: widget.snapshot,
        result: widget.result,
        progress: widget.progress,
      );
    } on OperationTraceProjectionException {
      return null;
    }
  }
}
