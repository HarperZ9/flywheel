import 'package:flutter/material.dart';

import '../client/bulletin_bounty_api.dart';
import '../client/bulletin_media_api.dart';
import '../client/gateway_client.dart';
import '../controllers/bulletin_media_authorizer.dart';
import '../controllers/journey_controller.dart';
import '../services/bulletin_media_cache.dart';
import '../widgets/bulletin_bounty_read_panel.dart';
import 'bulletin_media_workflow_view.dart';

export 'bulletin_media_workflow_view.dart' show BulletinMediaWorkflowView;

enum BulletinSection { media, bounties }

final class BulletinMediaView extends StatefulWidget {
  final GatewayClient? client;
  final JourneyController? journey;
  final BulletinMediaApi? api;
  final BulletinBountyApi? bountyApi;
  final BulletinSection initialSection;
  final BulletinPreparedAuthorizer? authorizer;
  final BulletinMediaLoader? mediaLoader;
  final String? initialJourneyRef, initialEventHead;

  const BulletinMediaView(
      {super.key,
      this.client,
      this.journey,
      this.api,
      this.bountyApi,
      this.initialSection = BulletinSection.media,
      this.authorizer,
      this.mediaLoader,
      this.initialJourneyRef,
      this.initialEventHead});

  @override
  State<BulletinMediaView> createState() => _BulletinMediaViewState();
}

final class _BulletinMediaViewState extends State<BulletinMediaView> {
  late BulletinSection _section = widget.initialSection;
  late final BulletinBountyApi _bountyApi =
      widget.bountyApi ?? HttpBulletinBountyApi();

  @override
  Widget build(BuildContext context) => Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
          child: SegmentedButton<BulletinSection>(
            segments: const [
              ButtonSegment(
                  value: BulletinSection.bounties, label: Text('Bounties')),
              ButtonSegment(value: BulletinSection.media, label: Text('Media')),
            ],
            selected: {_section},
            onSelectionChanged: (value) =>
                setState(() => _section = value.single),
          ),
        ),
        Expanded(
          child: _section == BulletinSection.bounties
              ? BulletinBountyReadPanel(api: _bountyApi)
              : BulletinMediaWorkflowView(
                  client: widget.client,
                  journey: widget.journey,
                  api: widget.api,
                  authorizer: widget.authorizer,
                  mediaLoader: widget.mediaLoader,
                  initialJourneyRef: widget.initialJourneyRef,
                  initialEventHead: widget.initialEventHead,
                ),
        ),
      ]);
}
