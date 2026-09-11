part of 'rowan_operation_controller.dart';

void _saveRowanSessionLocator({
  required JourneySessionStore? store,
  OperationSnapshot? snapshot,
  String? requestSha256,
  String? pendingRequestSha256,
}) {
  if (store == null) return;
  try {
    final prior = store.load();
    final journeyRef = snapshot?.journeyRef ?? prior?.journeyRef;
    if (journeyRef == null) return;
    final startingNewOperation = snapshot == null && requestSha256 != null;
    store.save(
      JourneySession(
        journeyRef: journeyRef,
        lens: prior?.lens ?? JourneyLens.verify,
        selectionRef: prior?.selectionRef,
        operationRef: startingNewOperation
            ? null
            : snapshot?.operationRef ?? prior?.operationRef,
        operationEventHeadSha256: startingNewOperation
            ? null
            : snapshot?.eventHeadSha256 ?? prior?.operationEventHeadSha256,
        operationRequestSha256: requestSha256 ??
            pendingRequestSha256 ??
            prior?.operationRequestSha256,
        detailsExpanded: prior?.detailsExpanded ?? false,
        recoveryVisible: prior?.recoveryVisible ?? false,
      ),
    );
  } on Object {
    // Session locators are hints; authoritative operation state is remote.
  }
}

String rowanRequestIdSha256(String clientRequestId) =>
    sha256.convert(utf8.encode(jsonEncode(clientRequestId))).toString();
