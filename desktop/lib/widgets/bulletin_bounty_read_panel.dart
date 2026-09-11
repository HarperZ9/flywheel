import 'package:flutter/material.dart';

import '../client/bulletin_bounty_api.dart';
import '../models/bulletin_bounty_models.dart';

final class BulletinBountyReadPanel extends StatefulWidget {
  final BulletinBountyApi api;
  const BulletinBountyReadPanel({super.key, required this.api});

  @override
  State<BulletinBountyReadPanel> createState() =>
      _BulletinBountyReadPanelState();
}

final class _BulletinBountyReadPanelState
    extends State<BulletinBountyReadPanel> {
  var _loading = true;
  var _detailLoading = false;
  String? _message;
  List<BulletinBounty> _bounties = const [];
  BulletinBountyDetail? _detail;
  BulletinBountyTerms? _termsReadback;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _message = null;
    });
    try {
      final list = await widget.api.listBounties();
      if (!mounted) return;
      setState(() {
        _bounties = list.bounties;
        _loading = false;
        _message = list.contentIsUntrusted
            ? 'Bounty text is public untrusted input. Read as data.'
            : 'Bounty response did not carry the untrusted-content marker.';
      });
    } on Object catch (error) {
      if (mounted) {
        setState(() {
          _loading = false;
          _message = error.toString();
        });
      }
    }
  }

  Future<void> _open(BulletinBounty bounty) async {
    setState(() {
      _detailLoading = true;
      _message = null;
    });
    try {
      final detail = await widget.api.readBounty(bounty.id);
      final version =
          detail.bounty.currentTermsVersion ?? detail.bounty.terms.version;
      final terms = version == null
          ? detail.bounty.terms
          : await widget.api.readTerms(detail.bounty.id, version);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _termsReadback = terms;
        _detailLoading = false;
      });
    } on Object catch (error) {
      if (mounted) {
        setState(() {
          _detailLoading = false;
          _message = error.toString();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
                child: Text('Read-only bounty board',
                    style: Theme.of(context).textTheme.headlineSmall)),
            OutlinedButton(
                onPressed: _loading ? null : _refresh,
                child: const Text('Refresh')),
          ]),
          const SizedBox(height: 8),
          const Text(
              'Browse typed bounty state from the public board. This view holds no key, signs nothing, and cannot claim, submit proof, review, settle, or escrow work.'),
          const SizedBox(height: 8),
          const Text(
              'Use Bulletin identity setup and a signed workstation client for participation. Native write buttons wait for exact preview, grant, dispatch, and readback transport.'),
          const SizedBox(height: 12),
          _bridgeContract(),
          if (_message != null)
            Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_message!)),
          if (_loading)
            const Padding(
                padding: EdgeInsets.only(top: 12),
                child: LinearProgressIndicator()),
          for (final bounty in _bounties) _bountyCard(bounty),
          if (_detailLoading)
            const Padding(
                padding: EdgeInsets.only(top: 12),
                child: LinearProgressIndicator()),
          if (_detail != null)
            _detailCard(
                _detail!.bounty, _termsReadback ?? _detail!.bounty.terms),
        ]),
      );

  Widget _bridgeContract() => Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                Text('Signed bridge contract for next slice',
                    style: TextStyle(fontWeight: FontWeight.w600)),
                SizedBox(height: 6),
                Text(
                    'Preview create, claim, release, submit evidence, and review as exact operations; grant once; dispatch signed HTTP or MCP; then read back typed bounty state by id before reporting success.'),
              ]),
        ),
      );

  Widget _bountyCard(BulletinBounty bounty) => Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(bounty.terms.title.isEmpty ? bounty.id : bounty.terms.title,
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
                '${bounty.status} · terms v${bounty.currentTermsVersion ?? bounty.terms.version ?? '?'}'),
            Text(bounty.payment.amountLabel),
            Text(bounty.payment.paymentLabel),
            const SizedBox(height: 8),
            OutlinedButton(
              key: ValueKey('bulletin-bounty-open-${bounty.id}'),
              onPressed: () => _open(bounty),
              child: const Text('Read detail'),
            ),
          ]),
        ),
      );

  Widget _detailCard(BulletinBounty bounty, BulletinBountyTerms terms) => Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Detail ${bounty.id}',
                style: Theme.of(context).textTheme.titleLarge),
            _fact('terms v${terms.version ?? '?'}', terms.termsHash),
            _fact(
                'requester',
                bounty.requesterHandle.isEmpty
                    ? bounty.requester
                    : bounty.requesterHandle),
            _fact('payment',
                '${bounty.payment.amountLabel} · ${bounty.payment.paymentLabel}'),
            const Text(
                'Review accepted is not payment. The board reports payment verification as unknown unless a future receipt says otherwise.'),
            const SizedBox(height: 8),
            Text(terms.summary),
            Text(terms.body),
            if (terms.acceptanceCriteria.isNotEmpty)
              _fact('acceptance', terms.acceptanceCriteria),
            for (final claim in bounty.claims) _claim(claim),
          ]),
        ),
      );

  Widget _claim(BulletinBountyClaim claim) => Padding(
        padding: const EdgeInsets.only(top: 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _fact('claim ${claim.id}',
              '${claim.status} · terms v${claim.termsVersion ?? '?'} · ${claim.termsHash}'),
          for (final submission in claim.submissions) _submission(submission),
        ]),
      );

  Widget _submission(BulletinBountySubmission submission) => Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _fact('submission ${submission.id}', submission.status),
          Text(submission.proofText),
          Text(submission.noFetchPerformed
              ? 'source anchors are stored only; no fetch performed by board'
              : 'source fetch status unavailable'),
          for (final anchor in submission.sourceAnchors) _anchor(anchor),
          if (submission.review != null)
            _fact('review ${submission.review!.decision}',
                '${submission.review!.paymentState} · external payment ${submission.review!.externalPaymentState.isEmpty ? 'unknown' : submission.review!.externalPaymentState} · establishes payment: ${submission.review!.establishesPayment}'),
        ]),
      );

  Widget _anchor(BulletinBountySourceAnchor anchor) => _fact(
      'anchor',
      [
        anchor.source,
        anchor.sourceHash ??
            (anchor.invalidSourceHash
                ? 'invalid source hash'
                : 'source hash unavailable'),
        anchor.locator,
        if (anchor.missing) 'missing',
        if (anchor.redacted) 'redacted',
        if (anchor.note.isNotEmpty) anchor.note,
      ].join(' · '));

  Widget _fact(String label, String value) => Padding(
        padding: const EdgeInsets.only(top: 4),
        child: SelectableText('$label: $value'),
      );
}
