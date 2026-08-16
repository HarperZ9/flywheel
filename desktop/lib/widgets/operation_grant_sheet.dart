import 'package:flutter/material.dart';

import '../controllers/gateway_operation_controller.dart';
import '../controllers/journey_controller.dart';
import '../models/gateway_grant_models.dart';
export '../models/gateway_grant_models.dart'
    show GatewayDestination, GatewayOperation;

Future<T?> showOperationGrantSheet<T>(
        BuildContext context,
        GatewayOperationController controller,
        Future<T> Function(Map<String, dynamic> finalBody) dispatch) =>
    showModalBottomSheet<T>(
        context: context,
        isScrollControlled: true,
        builder: (_) => _OperationGrantSheet<T>(controller, dispatch));

Future<T?> authorizeGatewayOperation<T>(
    BuildContext context,
    GatewayOperation operation,
    Future<T> Function(Map<String, dynamic> finalBody) dispatch,
    {required GatewayOperationSupplier currentOperation}) async {
  final outcome = await authorizeGatewayOperationDetailed(
      context, operation, dispatch,
      currentOperation: currentOperation);
  return outcome.value;
}

Future<GatewayAuthorizationOutcome<T>> authorizeGatewayOperationDetailed<T>(
    BuildContext context,
    GatewayOperation operation,
    Future<T> Function(Map<String, dynamic> finalBody) dispatch,
    {required GatewayOperationSupplier currentOperation}) async {
  final scope = GatewayOperationScope.maybeOf(context);
  if (scope == null) return const GatewayAuthorizationOutcome.denied();
  final result = await scope.authorize(context, operation, currentOperation,
      (body) async => await dispatch(body));
  if (result is GatewayAuthorizationOutcome) {
    if (result.failure != null) {
      return GatewayAuthorizationOutcome.failure(result.failure!);
    }
    if (result.denied) return const GatewayAuthorizationOutcome.denied();
    return GatewayAuthorizationOutcome.value(result.value as T);
  }
  return result == null
      ? const GatewayAuthorizationOutcome.denied()
      : GatewayAuthorizationOutcome.value(result as T);
}

GatewayOperationAuthorizer journeyGatewayAuthorizer(
        GatewayOperationController controller, JourneyController journey) =>
    (context, operation, currentOperation, dispatch) =>
        _authorizeJourneyOperation(context, controller, journey, operation,
            currentOperation, dispatch);

Future<Object?> _authorizeJourneyOperation(
    BuildContext context,
    GatewayOperationController controller,
    JourneyController journey,
    GatewayOperation operation,
    GatewayOperationSupplier currentOperation,
    Future<Object?> Function(Map<String, dynamic>) dispatch) async {
  GatewayJourneyBinding? currentBinding() {
    final active = journey.state.projection;
    return active == null ||
            active.invalidResponse ||
            journey.state.activeJourneyRef != active.journeyRef
        ? null
        : GatewayJourneyBinding(active.journeyRef, active.eventHeadSha256);
  }

  final binding = currentBinding();
  if (binding == null) return const GatewayAuthorizationOutcome.denied();
  final prepared = await controller.prepare(operation,
      binding: binding,
      currentOperation: currentOperation,
      currentBinding: currentBinding,
      refreshOnHeadConflict: journey.refreshActiveProjection);
  if (!context.mounted) return const GatewayAuthorizationOutcome.denied();
  if (!prepared) {
    final failure = controller.failure;
    return failure == null
        ? const GatewayAuthorizationOutcome.denied()
        : GatewayAuthorizationOutcome.failure(failure);
  }
  final result =
      await showOperationGrantSheet<Object?>(context, controller, dispatch);
  final failure = controller.failure;
  if (result == null && failure != null) {
    return GatewayAuthorizationOutcome.failure(failure);
  }
  return result == null
      ? const GatewayAuthorizationOutcome.denied()
      : GatewayAuthorizationOutcome.value(result);
}

Future<void> authorizeGatewayStream(
    BuildContext context,
    GatewayOperation operation,
    void Function(Map<String, dynamic> finalBody) dispatch,
    void Function() denied,
    {required GatewayOperationSupplier currentOperation}) async {
  final started =
      await authorizeGatewayOperation(context, operation, (body) async {
    dispatch(body);
    return true;
  }, currentOperation: currentOperation);
  if (started != true) denied();
}

final class _OperationGrantSheet<T> extends StatefulWidget {
  final GatewayOperationController controller;
  final Future<T> Function(Map<String, dynamic>) dispatch;
  const _OperationGrantSheet(this.controller, this.dispatch);
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
    final result = await widget.controller.approveAndDispatch(widget.dispatch);
    if (mounted && result != null) Navigator.pop(context, result);
  }

  @override
  Widget build(BuildContext context) {
    final proposal = widget.controller.proposal;
    final failure = widget.controller.failure;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: proposal == null
            ? Text(failure == null
                ? 'No current operation approval is available.'
                : '${failure.code}: ${failure.message}')
            : SingleChildScrollView(child: _content(proposal)),
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
          _line('Operation', proposal.summary.action),
          _line('Journey', proposal.summary.journeyRef),
          _line('Head', proposal.summary.eventHead),
          _line('Destination',
              '${proposal.summary.destination.kind}: ${proposal.summary.destination.ref}'),
          _line('Tool', proposal.summary.tool),
          _line('Operation digest', proposal.summary.operationSha256),
          _line('Arguments', proposal.summary.argumentsSha256),
          _refs('Data refs', proposal.summary.dataRefs),
          _refs('Credential refs', proposal.summary.credentialRefs),
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

  Widget _refs(String label, List<String> values) =>
      _line(label, values.isEmpty ? 'None' : values.join(', '));

  Widget _line(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text('$label: $value',
            maxLines: 2, overflow: TextOverflow.ellipsis),
      );
}
