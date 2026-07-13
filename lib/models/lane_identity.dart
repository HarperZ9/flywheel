// lane_identity.dart — presentation identity for each lane.
//
// The engine's roster carries name/organ/role/status/version; this map adds
// each product's own one-line identity (taken from its shipped README) and
// the natural data surface its deep view renders. Copy is feature-first and
// stays in the product's own words.

class LaneIdentity {
  final String title;
  final String identity;
  final String surface;
  const LaneIdentity(
      {required this.title, required this.identity, required this.surface});
}

const Map<String, LaneIdentity> laneIdentities = {
  'gather': LaneIdentity(
    title: 'Gather',
    identity:
        'Research intake that reaches the hard places: gated APIs, paywalls, '
        'JS-walled pages, scanned PDFs. Every block carries a source hash.',
    surface: 'corpus ledger',
  ),
  'crucible': LaneIdentity(
    title: 'Crucible',
    identity:
        'A judgment engine: register a thesis, steelman each claim, measure '
        'against a substrate, refine the weakest axis. Verdicts are pure '
        'functions, fail closed.',
    surface: 'verdict matrix',
  ),
  'index': LaneIdentity(
    title: 'Index',
    identity:
        'Maps a multi-repo workspace in seconds: dependency and symbol '
        'graphs, commit-pinned wikis, budgeted context envelopes. Fully '
        'offline.',
    surface: 'workspace atlas',
  ),
  'forum': LaneIdentity(
    title: 'Forum',
    identity:
        'Agent fleets with routing, quality gates, prose contracts, and a '
        'replayable causal ledger. Approval gates wait for a human.',
    surface: 'run room',
  ),
  'learn': LaneIdentity(
    title: 'Learn',
    identity:
        'Your own material, a runnable course: spaced repetition, retrieval '
        'practice, real grading. Study receipts re-verify.',
    surface: 'study dashboard',
  ),
  'telos': LaneIdentity(
    title: 'Telos',
    identity:
        'The shared workbench: durable state, native workstation control, a '
        'discovery forge. One MCP surface over the whole flagship family.',
    surface: 'workbench map',
  ),
  'local-model': LaneIdentity(
    title: 'Local model',
    identity:
        'The local proposer: a 14B coder behind the verified accept path. '
        'The oracle decides, the model proposes. No receipt, no accept.',
    surface: 'training and benchmark receipts',
  ),
};
