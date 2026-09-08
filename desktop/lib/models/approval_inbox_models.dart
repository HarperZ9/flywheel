import 'evidence_state.dart';
import 'gateway_grant_summary.dart';

export 'approval_active_work_models.dart';
export 'approval_inbox_list_models.dart';
export 'approval_review_models.dart';
export 'gateway_grant_models.dart' show GatewayGrantApproval;

import 'approval_review_models.dart';

const gatewayGrantCapabilitiesRequestSchema =
    'flywheel.gateway-grant-capabilities-request/v1';
const gatewayGrantCapabilitiesSchema = 'flywheel.gateway-grant-capabilities/v1';
const gatewayGrantReadRequestSchema = 'flywheel.gateway-grant-read-request/v1';
const gatewayGrantReadSchema = 'flywheel.gateway-grant-read/v1';
const gatewayGrantApprovalRequestSchema =
    'flywheel.gateway-grant-reviewed-approval-request/v1';
const gatewayGrantRejectRequestSchema =
    'flywheel.gateway-grant-reject-request/v1';
const gatewayGrantRejectionSchema = 'flywheel.gateway-grant-rejection/v1';

final _statePattern = RegExp(r'^[a-z][a-z0-9_]{0,63}$');

final class GatewayGrantCapabilities extends DefensiveModel {
  final bool reviewedApproval, proposalList, proposalRead, durableReject;
  final int reviewMaxBytes;

  GatewayGrantCapabilities._(
      this.reviewedApproval,
      this.proposalList,
      this.proposalRead,
      this.durableReject,
      this.reviewMaxBytes,
      super.parseIssues);

  bool get ready =>
      !invalidResponse &&
      reviewedApproval &&
      proposalList &&
      proposalRead &&
      durableReject &&
      reviewMaxBytes > 0;

  factory GatewayGrantCapabilities.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, gatewayGrantCapabilitiesSchema, issues);
    final maxBytes = readValue<int>(json, 'review_max_bytes', issues, 0);
    if (maxBytes < 1 || maxBytes > 1048576) {
      addParseIssue(issues, 'review_max_bytes', maxBytes);
    }
    return GatewayGrantCapabilities._(
        readValue<bool>(json, 'reviewed_approval', issues, false),
        readValue<bool>(json, 'proposal_list', issues, false),
        readValue<bool>(json, 'proposal_read', issues, false),
        readValue<bool>(json, 'durable_reject', issues, false),
        maxBytes,
        issues);
  }
}

final class GatewayGrantRead extends DefensiveModel {
  final String serverTime, proposalState, derivedState, unavailableReason;
  final String recordSha256Field, expiresAt;
  final bool reviewAvailable;
  final GatewayGrantReview? review;

  GatewayGrantRead._(
      this.serverTime,
      this.proposalState,
      this.derivedState,
      this.recordSha256Field,
      this.expiresAt,
      this.reviewAvailable,
      this.unavailableReason,
      this.review,
      super.parseIssues);

  bool get approvable =>
      !invalidResponse &&
      reviewAvailable &&
      proposalState == 'prepared' &&
      derivedState == 'pending' &&
      review != null &&
      !review!.invalidResponse;
  String get proposalRef => review?.proposalRef ?? '';
  String get recordSha256 => review?.recordSha256 ?? recordSha256Field;
  String get operationRef => review?.operationRef ?? '';

  factory GatewayGrantRead.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, gatewayGrantReadSchema, issues);
    final available = readValue<bool>(json, 'review_available', issues, false);
    GatewayGrantReview? review;
    final rawReview = json['review'];
    if (available) {
      if (rawReview is Map<String, Object?>) {
        review = GatewayGrantReview.fromJson(rawReview);
        issues.addAll(review.parseIssues);
      } else {
        addParseIssue(issues, 'review', rawReview);
      }
    } else if (rawReview != null) {
      addParseIssue(issues, 'review', rawReview);
    }
    return GatewayGrantRead._(
        readText(json, 'server_time', issues),
        readText(json, 'proposal_state', issues, pattern: _statePattern),
        readText(json, 'derived_state', issues, pattern: _statePattern),
        readText(json, 'record_sha256', issues,
            optional: true, pattern: sha256Pattern),
        readText(json, 'expires_at', issues, optional: true),
        available,
        readText(json, 'unavailable_reason', issues, optional: true),
        review,
        issues);
  }
}

final class GatewayGrantRejection extends DefensiveModel {
  final String proposalRef, proposalState, recordSha256;
  GatewayGrantRejection._(this.proposalRef, this.proposalState,
      this.recordSha256, super.parseIssues);

  factory GatewayGrantRejection.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    exactGatewayFields(
        json,
        const {'schema', 'proposal_ref', 'proposal_state', 'record_sha256'},
        issues,
        'rejection');
    expectSchema(json, gatewayGrantRejectionSchema, issues);
    return GatewayGrantRejection._(
        readText(json, 'proposal_ref', issues, pattern: proposalRefPattern),
        readText(json, 'proposal_state', issues, pattern: _statePattern),
        readText(json, 'record_sha256', issues, pattern: sha256Pattern),
        issues);
  }
}
