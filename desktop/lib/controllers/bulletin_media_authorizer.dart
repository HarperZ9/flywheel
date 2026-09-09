import 'package:flutter/widgets.dart';

import '../controllers/gateway_operation_controller.dart';
import '../models/bulletin_media_models.dart';

typedef BulletinPreparedAuthorizer
    = Future<GatewayAuthorizationOutcome<BulletinMediaPublishResult>> Function(
        BuildContext context,
        BulletinMediaPreviewResponse preview,
        GatewayOperationSupplier currentOperation,
        Future<BulletinMediaPublishResult> Function(Map<String, dynamic>)
            dispatch);
