import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/service_desk_review.dart';

void main() {
  test('parses complete review and keeps claimed separate from recomputed', () {
    final result = ServiceDeskReviewResult.fromJson(_routeBody('pass'));

    expect(result.errorCode, isNull);
    expect(result.review!.claimedAllRecordedCasesPassed, isTrue);
    expect(result.review!.observedState, 'pass');
    expect(result.review!.externalTrustState, 'not_established');
    expect(
      result.review!.limits,
      contains('Recorded case flags are not rerun by this review.'),
    );
  });

  test('partial older product reports are upgrade required, not pass', () {
    final result = ServiceDeskReviewResult.fromJson({
      'schema': ServiceDeskReviewResult.schemaName,
      'environment_id': 'service-desk-incident/v1',
      'artifact_dir_ref': 'runs/a',
      'artifact_label': 'a',
      'report': {
        'schema': ServiceDeskReview.reportSchema,
        'verification': {
          'schema': ServiceDeskReview.verificationSchema,
          'observed_state': 'pass',
          'failure_codes': <String>[],
        },
        'claimed_outcome': <String, Object?>{},
        'recomputed_outcome': <String, Object?>{},
        'evidence_layers': <String, Object?>{},
        'limits': <String>[],
      },
    });

    expect(result.review, isNull);
    expect(result.errorCode, 'PRODUCT_UPGRADE_REQUIRED');
  });

  test('gateway errors remain visible to the panel', () {
    final result = ServiceDeskReviewResult.fromJson({
      'schema': 'flywheel.evidence-transport-error/v1',
      'error': {
        'code': 'PRODUCT_UNAVAILABLE',
        'message': 'install the ServiceDesk product',
      },
    });

    expect(result.review, isNull);
    expect(result.errorCode, 'PRODUCT_UNAVAILABLE');
    expect(result.errorMessage, contains('install'));
  });
}

Map<String, Object?> _routeBody(String observedState) => {
      'schema': ServiceDeskReviewResult.schemaName,
      'environment_id': 'service-desk-incident/v1',
      'artifact_dir_ref': 'runs/service-desk-incident-v1-a',
      'artifact_label': 'service-desk-incident-v1-a',
      'report': {
        'schema': ServiceDeskReview.reportSchema,
        'artifact_label': 'service-desk-incident-v1-a',
        'artifact_dir_ref': 'runs/service-desk-incident-v1-a',
        'verification': {
          'schema': ServiceDeskReview.verificationSchema,
          'artifact_dir_ref': 'runs/service-desk-incident-v1-a',
          'observed_state': observedState,
          'failure_codes': observedState == 'pass'
              ? <String>[]
              : ['target_incident_not_open'],
        },
        'claimed_outcome': {
          'all_recorded_cases_passed': true,
          'recorded_case_count': 1,
          'basis':
              'receipt-recorded case flags; not accepted as semantic truth',
        },
        'recomputed_outcome': {
          'observed_state': observedState,
          'failure_codes': observedState == 'pass'
              ? <String>[]
              : ['target_incident_not_open'],
          'basis':
              'source_integrity, synthetic_task_check, and record_consistency',
        },
        'evidence_layers': {
          'source_integrity': {
            'observed_state': 'pass',
            'failure_codes': <String>[],
          },
          'synthetic_task_check': {
            'observed_state': observedState,
            'failure_codes': observedState == 'pass'
                ? <String>[]
                : ['target_incident_not_open'],
            'authorization': 'unchecked',
            'log_origin': 'submitted_untrusted',
          },
          'record_consistency': {
            'observed_state': 'pass',
            'failure_codes': <String>[],
          },
          'externally_trusted_evidence': {
            'observed_state': 'not_established',
            'reason':
                'No external signature, trusted timestamp, or independent evidence anchor is present in this bundle.',
          },
        },
        'limits': [
          'Recorded case flags are not rerun by this review.',
          'A fabricated complete outcome with matching fabricated logs could satisfy the synthetic task check.',
        ],
      },
    };
