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
        'The deep-research intake half: reach the hard places (gated APIs, '
        'paywalls, JS-walled pages, scanned PDFs), federate the scholarly '
        'record, and build a durable corpus where every block carries a '
        'source hash. Paired with Crucible, this is the experimentation bench.',
    surface: 'research corpus + federation',
  ),
  'crucible': LaneIdentity(
    title: 'Crucible',
    identity:
        'The deep-research judgment half: register a thesis, steelman each '
        'claim, run the experiment, measure against a substrate, refine the '
        'weakest axis. Verdicts are pure functions that fail closed, so an '
        'experiment can conclude UNVERIFIABLE instead of overclaiming.',
    surface: 'experiment bench + verdict matrix',
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
        'A full academy: academic tutoring, programming instruction, and a '
        'knowledge academy over your own material. Spaced repetition, '
        'retrieval practice, prerequisite readiness, and real grading, with '
        'a mastery verdict and study receipts that re-verify.',
    surface: 'tutor + courses + mastery',
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
  'relay': LaneIdentity(
    title: 'Relay',
    identity:
        'A zero-dependency coding agent with model failover and a '
        'hash-chained session ledger. Runs on any endpoint (local, '
        'Ollama, hosted), with gated tools and re-verifiable receipts. '
        'Serves a remote MCP endpoint for phone access via connectors.',
    surface: 'agent runs + remote MCP',
  ),
  'plexus': LaneIdentity(
    title: 'Plexus',
    identity:
        'Capability discovery and auto-wiring for a toolchain. Point it at a '
        'set of tools and it reads what each one emits and consumes, then '
        'wires producer to consumer into a runnable pipeline. MCP says which '
        'tools exist; plexus says how their outputs plug together.',
    surface: 'capability graph + pipeline plan',
  ),
  'mneme': LaneIdentity(
    title: 'Mneme',
    identity:
        'Layered memory and hybrid retrieval, with the three things most '
        'memory systems leave out: every memory carries its provenance, every '
        'recall reproduces its ranking, and a stale memory flags its own '
        'drift.',
    surface: 'recall receipts + drift verdicts',
  ),
  'calibrate-pro': LaneIdentity(
    title: 'Calibrate Pro',
    identity:
        'Make screens match the work. Display discovery, calibration targets, '
        'DDC/CI, ICC and LUT tooling, and verification reports behind one '
        'preview-and-confirm workflow. A sensorless value is labelled an '
        'estimate; a measured value keeps its evidence source.',
    surface: 'display catalog + readiness doctor',
  ),
  'canon': LaneIdentity(
    title: 'Canon',
    identity:
        'One record for your memory bank and your personality, shared across '
        'every model and every tool. Each instruction file is rendered from '
        'that record inside one marked region, and every byte outside the '
        'region is left alone.',
    surface: 'authored blocks + rendered surfaces',
  ),
  'bulletin': LaneIdentity(
    title: 'Bulletin',
    identity:
        'A message board where the accounts belong to agents. No signup form '
        'and no email confirmation: identity is an Ed25519 key, every write '
        'carries an HTTP Message Signature, and an agent joins by generating '
        'a key and proving one small amount of work.',
    surface: 'rooms, posts, and replies',
  ),
  'accountable-surface': LaneIdentity(
    title: 'Accountable surface',
    identity:
        'Perceive, gate, act, verify, journal. An agent reads a target as '
        'structure, proposes an action, passes an operator-loaded gate, acts '
        'through a bounded effector, re-perceives to check what happened, and '
        'records the whole path.',
    surface: 'grant gate + action journal',
  ),
};
