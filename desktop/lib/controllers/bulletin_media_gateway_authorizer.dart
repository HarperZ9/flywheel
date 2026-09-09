import 'package:flutter/material.dart';

import '../models/bulletin_media_models.dart';
import '../widgets/operation_grant_sheet.dart';
import 'gateway_operation_controller.dart';

Future<GatewayAuthorizationOutcome<BulletinMediaPublishResult>>
    authorizeBulletinMediaWithGateway(
  BuildContext context, {
  required BulletinMediaPreviewResponse preview,
  required GatewayOperationController? controller,
  required GatewayJourneyBinding? binding,
  required GatewayOperationSupplier currentOperation,
  required GatewayJourneyBinding? Function() currentBinding,
  required Future<void> Function()? refreshOnHeadConflict,
  required Future<BulletinMediaPublishResult> Function(Map<String, dynamic>)
      dispatch,
}) async {
  final operation = preview.operation;
  if (operation == null || controller == null || binding == null) {
    return const GatewayAuthorizationOutcome.failure(GatewayOperationFailure(
        'INVALID_RESPONSE', 'Prepared gateway proposal was invalid'));
  }
  final adopted = controller.adoptPreparedProposal(
    operation,
    preview.proposal,
    binding: binding,
    currentOperation: currentOperation,
    currentBinding: currentBinding,
    refreshOnHeadConflict: refreshOnHeadConflict,
  );
  if (!adopted) {
    final failure = controller.failure;
    return failure == null
        ? const GatewayAuthorizationOutcome.denied()
        : GatewayAuthorizationOutcome.failure(failure);
  }
  final value = await showOperationGrantSheet<BulletinMediaPublishResult>(
      context, controller, dispatch);
  final failure = controller.failure;
  if (value == null && failure != null) {
    return GatewayAuthorizationOutcome.failure(failure);
  }
  return value == null
      ? const GatewayAuthorizationOutcome.denied()
      : GatewayAuthorizationOutcome.value(value);
}
