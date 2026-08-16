import 'package:flutter/material.dart';

import '../controllers/gateway_operation_controller.dart';
import '../controllers/journey_controller.dart';
import '../models/gateway_grant_models.dart';
export '../models/gateway_grant_models.dart' show GatewayOperation;

Future<T?> showOperationGrantSheet<T>(
        BuildContext context,
        GatewayOperationController controller,
        Future<T> Function(Map<String, dynamic> finalBody) dispatch,
        {bool Function(GatewayGrantProposal proposal)? stillCurrent}) =>
    showModalBottomSheet<T>(
        context: context,
        isScrollControlled: true,
        builder: (_) =>
            _OperationGrantSheet<T>(controller, dispatch, stillCurrent));

Future<T?> authorizeGatewayOperation<T>(
    BuildContext context,
    GatewayOperation operation,
    Future<T> Function(Map<String, dynamic> finalBody) dispatch) async {
  final scope = GatewayOperationScope.maybeOf(context);
  if (scope == null) return null;
  final result = await scope.authorize(
      context, operation, (body) async => await dispatch(body));
  return result as T?;
}

GatewayOperationAuthorizer journeyGatewayAuthorizer(
        GatewayOperationController controller, JourneyController journey) =>
    (context, operation, dispatch) => _authorizeJourneyOperation(
        context, controller, journey, operation, dispatch);

Future<Object?> _authorizeJourneyOperation(
    BuildContext context,
    GatewayOperationController controller,
    JourneyController journey,
    GatewayOperation operation,
    Future<Object?> Function(Map<String, dynamic>) dispatch) async {
  final active = journey.state.projection;
  if (active == null ||
      active.invalidResponse ||
      journey.state.activeJourneyRef != active.journeyRef) {
    return null;
  }
  final prepared = await controller.prepare(operation,
      journeyRef: active.journeyRef, eventHead: active.eventHeadSha256);
  if (!prepared || !context.mounted) return null;
  return showOperationGrantSheet<Object?>(context, controller, dispatch,
      stillCurrent: (proposal) {
    final current = journey.state.projection;
    return current != null &&
        journey.state.activeJourneyRef == proposal.journeyRef &&
        current.journeyRef == proposal.journeyRef &&
        current.eventHeadSha256 == proposal.eventHead;
  });
}

Future<void> authorizeGatewayStream(
    BuildContext context,
    GatewayOperation operation,
    void Function(Map<String, dynamic> finalBody) dispatch,
    void Function() denied) async {
  final started =
      await authorizeGatewayOperation(context, operation, (body) async {
    dispatch(body);
    return true;
  });
  if (started != true) denied();
}

final class _OperationGrantSheet<T> extends StatefulWidget {
  final GatewayOperationController controller;
  final Future<T> Function(Map<String, dynamic>) dispatch;
  final bool Function(GatewayGrantProposal)? stillCurrent;
  const _OperationGrantSheet(this.controller, this.dispatch, this.stillCurrent);
  @override
  State<_OperationGrantSheet<T>> createState() =>
      _OperationGrantSheetState<T>();
}

final class _OperationGrantSheetState<T>
    extends State<_OperationGrantSheet<T>> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_changed);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_changed);
    widget.controller.invalidate();
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Future<void> _approve() async {
    final proposal = widget.controller.proposal;
    if (proposal == null || widget.stillCurrent?.call(proposal) == false) {
      widget.controller.invalidate();
      return;
    }
    final result = await widget.controller.approveAndDispatch(widget.dispatch);
    if (mounted && result != null) Navigator.pop(context, result);
  }

  @override
  Widget build(BuildContext context) {
    final proposal = widget.controller.proposal;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: proposal == null
            ? const Text('No current operation approval is available.')
            : _content(proposal),
      ),
    );
  }

  Widget _content(GatewayGrantProposal proposal) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Approve one external operation',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          _line('Operation', proposal.summary.operation),
          _line('Journey', proposal.summary.journeyRef),
          _line('Head', proposal.summary.eventHead),
          _line('Tool', proposal.summary.tool),
          _line('Arguments', proposal.summary.argumentsSha256),
          _line('Effect', proposal.summary.effect),
          _line('Expires', proposal.summary.expiresAt),
          const SizedBox(height: 12),
          Wrap(
              spacing: 8,
              children: proposal.summary.scopes
                  .map((scope) => Chip(label: Text(scope)))
                  .toList()),
          const SizedBox(height: 20),
          Row(mainAxisAlignment: MainAxisAlignment.end, children: [
            TextButton(
                onPressed: widget.controller.pending
                    ? null
                    : () => Navigator.pop(context),
                child: const Text('Deny')),
            const SizedBox(width: 12),
            FilledButton(
                onPressed: widget.controller.pending ? null : _approve,
                child: const Text('Approve once')),
          ]),
        ],
      );

  Widget _line(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text('$label: $value',
            maxLines: 2, overflow: TextOverflow.ellipsis),
      );
}
