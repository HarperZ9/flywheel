import 'dart:io';

import 'bulletin_media_review.dart';
import 'evidence_state.dart';

part 'gateway_destination.dart';
part 'gateway_grant_proposal.dart';

const gatewayGrantSummarySchema = 'flywheel.gateway-grant-summary/v1';
const gatewayProposalSchema = 'flywheel.gateway-grant-proposal/v1';

/// Destination kinds whose ref is a directory on this machine. Every other
/// kind names a model, an endpoint, a plugin: text that is safe to show
/// anywhere. These three name a path, so they are read with the narrower
/// local-path rule instead of being blanked. A credential scan with no root
/// reads the environment and names it that way, which the same rule accepts.
const pathDestinationKinds = {'suite', 'workspace', 'scan'};
final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');
final _credentialRef = RegExp(r'^cred_[0-9a-f]{32}$');
final _dataRef = RegExp(r'^data_[A-Za-z0-9._:-]{0,123}$');

final class GatewayJourneyBinding {
  final String journeyRef, eventHead;
  const GatewayJourneyBinding(this.journeyRef, this.eventHead);
  @override
  bool operator ==(Object other) =>
      other is GatewayJourneyBinding &&
      journeyRef == other.journeyRef &&
      eventHead == other.eventHead;
  @override
  int get hashCode => Object.hash(journeyRef, eventHead);
}

final class GatewayGrantSummary extends DefensiveModel {
  final String action, journeyRef, eventHead, tool, operationSha256;
  final String argumentsSha256, effect, expiresAt;
  final BulletinMediaReview? bulletinMediaReview;
  final GatewayDestination destination;
  final List<String> scopes, dataRefs, credentialRefs;

  GatewayGrantSummary._(
    this.action,
    this.journeyRef,
    this.eventHead,
    this.destination,
    this.tool,
    this.operationSha256,
    this.argumentsSha256,
    this.scopes,
    this.dataRefs,
    this.credentialRefs,
    this.effect,
    this.expiresAt,
    this.bulletinMediaReview,
    super.parseIssues,
  );

  factory GatewayGrantSummary.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    const fields = {
      'schema',
      'action',
      'journey_ref',
      'expected_event_head',
      'destination',
      'tool',
      'operation_sha256',
      'arguments_sha256',
      'scopes',
      'data_refs',
      'credential_refs',
      'effect',
      'expires_at',
    };
    exactGatewayFields(
      json,
      json.containsKey('bulletin_media_review')
          ? {...fields, 'bulletin_media_review'}
          : fields,
      issues,
      'summary',
    );
    expectSchema(json, gatewayGrantSummarySchema, issues);
    final bulletinReview = json['bulletin_media_review'] is Map<String, Object?>
        ? BulletinMediaReview.fromJson(
            json['bulletin_media_review'] as Map<String, Object?>,
          )
        : null;
    if (json.containsKey('bulletin_media_review') && bulletinReview == null) {
      addParseIssue(
        issues,
        'bulletin_media_review',
        json['bulletin_media_review'],
      );
    }
    if (bulletinReview != null) issues.addAll(bulletinReview.parseIssues);
    return GatewayGrantSummary._(
      readText(json, 'action', issues),
      readText(json, 'journey_ref', issues, pattern: _journeyRef),
      readText(json, 'expected_event_head', issues, pattern: sha256Pattern),
      GatewayDestination.fromJson(json['destination'], issues, 'destination'),
      readText(json, 'tool', issues),
      readText(json, 'operation_sha256', issues, pattern: sha256Pattern),
      readText(json, 'arguments_sha256', issues, pattern: sha256Pattern),
      readStringList(json['scopes'], 'scopes', issues),
      readGatewayDataRefs(json['data_refs'], issues),
      readGatewayCredentialRefs(json['credential_refs'], issues),
      readText(json, 'effect', issues),
      readText(json, 'expires_at', issues),
      bulletinReview,
      issues,
    );
  }
}

List<String> readGatewayCredentialRefs(Object? raw, List<ParseIssue> issues) {
  final values = readStringList(raw, 'credential_refs', issues);
  if (values.any((value) => !_credentialRef.hasMatch(value)) ||
      values.toSet().length != values.length) {
    addParseIssue(issues, 'credential_refs', raw);
    return const [];
  }
  return values;
}

List<String> readGatewayDataRefs(Object? raw, List<ParseIssue> issues) {
  final values = readStringList(raw, 'data_refs', issues);
  if (values.any((value) => !_dataRef.hasMatch(value)) ||
      values.toSet().length != values.length) {
    addParseIssue(issues, 'data_refs', raw);
    return const [];
  }
  return values;
}

void exactGatewayFields(
  Map<String, Object?> value,
  Set<String> fields,
  List<ParseIssue> issues,
  String field,
) {
  if (value.keys.toSet().length != fields.length ||
      !value.keys.every(fields.contains)) {
    addParseIssue(issues, field, value.keys.toList());
  }
}

bool sameGatewayStringList(List<String> left, List<String> right) =>
    left.length == right.length &&
    left.indexed.every((item) => item.$2 == right[item.$1]);

bool sameGatewayValue(Object? left, Object? right) {
  if (left is Map && right is Map) {
    return left.length == right.length &&
        left.entries.every(
          (entry) =>
              right.containsKey(entry.key) &&
              sameGatewayValue(entry.value, right[entry.key]),
        );
  }
  if (left is List && right is List) {
    return left.length == right.length &&
        left.indexed.every(
          (entry) => sameGatewayValue(entry.$2, right[entry.$1]),
        );
  }
  return left == right;
}

int gatewayValueHash(Object? value) {
  if (value is Map) {
    final keys = value.keys.map((key) => key.toString()).toList()..sort();
    return Object.hashAll(
      keys.map((key) => Object.hash(key, gatewayValueHash(value[key]))),
    );
  }
  if (value is List) return Object.hashAll(value.map(gatewayValueHash));
  return value.hashCode;
}
