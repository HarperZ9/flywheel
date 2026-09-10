import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/service_desk_review.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ServiceDeskReviewPanel extends StatefulWidget {
  final GatewayClient client;
  const ServiceDeskReviewPanel({super.key, required this.client});

  @override
  State<ServiceDeskReviewPanel> createState() => _ServiceDeskReviewPanelState();
}

class _ServiceDeskReviewPanelState extends State<ServiceDeskReviewPanel> {
  final _artifactRef = TextEditingController();
  ServiceDeskReviewResult? _result;
  bool _busy = false;

  @override
  void dispose() {
    _artifactRef.dispose();
    super.dispose();
  }

  Future<void> _review() async {
    final ref = _artifactRef.text.trim();
    if (ref.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _result = null;
    });
    try {
      final result = await widget.client.serviceDeskIncidentReview(ref);
      if (mounted) setState(() => _result = result);
    } catch (e) {
      if (mounted) {
        setState(
          () => _result = ServiceDeskReviewResult.fromJson({
            'schema': 'flywheel.evidence-transport-error/v1',
            'error': {'code': 'GATEWAY_ERROR', 'message': '$e'},
          }),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('review ServiceDesk evidence'),
          const SizedBox(height: FwLayout.s1),
          Text(
            'Select a ServiceDesk incident artifact directory by its reference '
            'under the gateway run root. Absolute paths, drive paths, file:// '
            'references, links, junctions, and traversal are refused before '
            'the review runs.',
            style: TextStyle(fontSize: 12.5, color: t.inkMuted),
          ),
          const SizedBox(height: FwLayout.s3),
          TextField(
            controller: _artifactRef,
            enabled: !_busy,
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration: const InputDecoration(
              isDense: true,
              labelText: 'artifact directory ref',
              hintText: 'runs/service-desk-incident-v1-...',
            ),
          ),
          const SizedBox(height: FwLayout.s3),
          FilledButton(
            onPressed: _busy ? null : _review,
            child: Text(_busy ? 'Reviewing...' : 'Review evidence'),
          ),
          const SizedBox(height: FwLayout.s3),
          _body(t),
        ],
      ),
    );
  }

  Widget _body(FwTokens t) {
    final result = _result;
    if (result == null) {
      return const HonestNull(
        'No ServiceDesk artifact directory has been reviewed in this panel yet.',
      );
    }
    if (result.review == null) {
      final code = result.errorCode ?? 'GATEWAY_ERROR';
      final message = result.errorMessage ?? 'ServiceDesk review unavailable.';
      return HonestNull('$code: $message');
    }
    return _reviewResult(t, result.review!);
  }

  Widget _reviewResult(FwTokens t, ServiceDeskReview review) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: FwLayout.s2,
          runSpacing: FwLayout.s2,
          children: [
            VerdictPill(
              review.displayState,
              status: serviceDeskStatusForState(review.observedState),
            ),
            VerdictPill(
              'external trust ${_plainState(review.externalTrustState)}',
              status: 'unverifiable',
            ),
          ],
        ),
        const SizedBox(height: FwLayout.s3),
        _outcomes(t, review),
        const SizedBox(height: FwLayout.s3),
        _layers(review),
        const SizedBox(height: FwLayout.s3),
        _failures(review),
        const SizedBox(height: FwLayout.s3),
        _limits(review),
      ],
    );
  }

  Widget _outcomes(FwTokens t, ServiceDeskReview review) {
    final count = review.recordedCaseCount == null
        ? ''
        : ' (${review.recordedCaseCount} recorded case)';
    return AdaptiveTiles(
      children: [
        HairlineCard(
          recessed: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Kicker('claimed outcome'),
              const SizedBox(height: FwLayout.s2),
              Text(
                'recorded case flags '
                '${review.claimedAllRecordedCasesPassed ? 'passed' : 'failed'}'
                '$count',
                style: TextStyle(color: t.ink),
              ),
              const SizedBox(height: FwLayout.s1),
              Text(
                review.claimedBasis,
                style: TextStyle(fontSize: 12, color: t.inkMuted),
              ),
            ],
          ),
        ),
        HairlineCard(
          recessed: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Kicker('recomputed outcome'),
              const SizedBox(height: FwLayout.s2),
              Text(
                'recomputed ${_plainState(review.observedState)}',
                style: TextStyle(
                  color: t.statusColor(
                    serviceDeskStatusForState(review.observedState),
                  ),
                ),
              ),
              const SizedBox(height: FwLayout.s1),
              Text(
                review.recomputedBasis,
                style: TextStyle(fontSize: 12, color: t.inkMuted),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _layers(ServiceDeskReview review) {
    final layers = {
      'source integrity': review.sourceIntegrityState,
      'synthetic task': review.syntheticTaskState,
      'record consistency': review.recordConsistencyState,
      'external trust': review.externalTrustState,
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('evidence layers'),
        const SizedBox(height: FwLayout.s2),
        Wrap(
          spacing: FwLayout.s2,
          runSpacing: FwLayout.s2,
          children: [
            for (final entry in layers.entries)
              VerdictPill(
                '${entry.key} ${_plainState(entry.value)}',
                status: serviceDeskStatusForState(entry.value),
              ),
          ],
        ),
        const SizedBox(height: FwLayout.s2),
        HonestNull(
          '${review.externalTrustReason} Synthetic log origin is '
          '${review.syntheticLogOrigin}; authorization is '
          '${review.syntheticAuthorization}.',
        ),
      ],
    );
  }

  Widget _failures(ServiceDeskReview review) {
    if (review.failureCodes.isEmpty) {
      return const HonestNull('No recomputed failure codes.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('failure codes'),
        const SizedBox(height: FwLayout.s2),
        Wrap(
          spacing: FwLayout.s2,
          runSpacing: FwLayout.s2,
          children: [
            for (final code in review.failureCodes)
              VerdictPill(code, status: 'drift'),
          ],
        ),
      ],
    );
  }

  Widget _limits(ServiceDeskReview review) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('limits'),
        const SizedBox(height: FwLayout.s2),
        for (final limit in review.limits)
          Padding(
            padding: const EdgeInsets.only(bottom: FwLayout.s1),
            child: Text('- $limit'),
          ),
      ],
    );
  }

  String _plainState(String value) => value.replaceAll('_', ' ');
}
