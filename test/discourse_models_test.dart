// DiscourseDigest: the typed reading of a flywheel.discourse-digest/v1 envelope.
// Sentiment is a weight (parsed as shares), never a verdict; the verify status
// is the one verdict. Parsing is defensive: missing fields degrade, never crash.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/discourse.dart';

void main() {
  test('DiscourseDigest parses a full envelope', () {
    final d = DiscourseDigest.fromEnvelope({
      'schema': 'flywheel.discourse-digest/v1',
      'verified': true,
      'result': {
        'responds_to': 'vid9',
        'n_items': 116,
        'method': {
          'engagement_coverage': {'present': 116, 'total': 116},
          'coarseness': 'lexicon sentiment is English-only and literal',
        },
        'receipt': {'digest_sha256': 'abc123'},
        'themes': [
          {
            'label': 'sound / design',
            'size': 12,
            'weighted_score': 42.5,
            'sentiment': {'pos': 0.5, 'neg': 0.17, 'neu': 0.33, 'mean_compound': 0.1},
            'dissent': 'c7',
          },
        ],
      },
    });
    expect(d.verified, isTrue);
    expect(d.respondsTo, 'vid9');
    expect(d.nItems, 116);
    expect(d.engagementPresent, 116);
    expect(d.engagementTotal, 116);
    expect(d.engagementComplete, isTrue);
    expect(d.coarseness, contains('English-only'));
    expect(d.digestSha, 'abc123');
    expect(d.themes, hasLength(1));
    expect(d.themes.first.label, 'sound / design');
    expect(d.themes.first.size, 12);
    expect(d.themes.first.posShare, 0.5);
    expect(d.themes.first.dissent, 'c7');
  });

  test('a partial envelope degrades instead of crashing', () {
    final d = DiscourseDigest.fromEnvelope({'result': {}});
    expect(d.verified, isFalse);
    expect(d.nItems, 0);
    expect(d.themes, isEmpty);
    expect(d.engagementComplete, isFalse); // total 0 -> not complete, honest null
    expect(d.digestSha, isEmpty);
  });

  test('absent engagement coverage reads as incomplete, not a fake full', () {
    final d = DiscourseDigest.fromEnvelope({
      'verified': true,
      'result': {
        'n_items': 3,
        'method': {'engagement_coverage': {'present': 0, 'total': 3}},
        'themes': [],
      },
    });
    expect(d.engagementPresent, 0);
    expect(d.engagementTotal, 3);
    expect(d.engagementComplete, isFalse);
  });

  test('a dissent-free theme parses dissent as null', () {
    final d = DiscourseDigest.fromEnvelope({
      'result': {
        'themes': [
          {'label': 'x', 'size': 2, 'weighted_score': 1.0, 'sentiment': {}, 'dissent': null},
        ],
      },
    });
    expect(d.themes.first.dissent, isNull);
    expect(d.themes.first.posShare, 0.0);
  });

  test('a theme carries its controversy score, degrading to zero when absent', () {
    final d = DiscourseDigest.fromEnvelope({
      'result': {
        'themes': [
          {'label': 'battery', 'size': 4, 'weighted_score': 9.0, 'sentiment': {},
           'dissent': 'c3', 'controversy': 0.62},
          {'label': 'screen', 'sentiment': {}}, // no controversy -> 0.0, not a crash
        ],
      },
    });
    expect(d.themes.first.controversy, 0.62);
    expect(d.themes.last.controversy, 0.0);
  });

  test('contested aspects parse as the topics the crowd is split on', () {
    final d = DiscourseDigest.fromEnvelope({
      'result': {
        'themes': [],
        'contested': [
          {'term': 'battery', 'mentions': 5, 'pos': 0.2, 'neg': 0.6, 'contested': 0.54},
          {'partial': true}, // missing fields degrade, never crash
        ],
      },
    });
    expect(d.contested, hasLength(2));
    expect(d.contested.first.term, 'battery');
    expect(d.contested.first.mentions, 5);
    expect(d.contested.first.negShare, 0.6);
    expect(d.contested.first.score, 0.54);
    expect(d.contested.last.term, isEmpty);
    expect(d.contested.last.mentions, 0);
  });

  test('a digest with no contested aspects reads as an empty list', () {
    final d = DiscourseDigest.fromEnvelope({'result': {'themes': []}});
    expect(d.contested, isEmpty);
  });

  test('CorpusRef.listFrom parses discovered corpora defensively', () {
    final list = CorpusRef.listFrom({
      'root': '/r',
      'corpora': [
        {'path': '/r/harari', 'name': 'harari', 'comments': 116, 'subject': 'AI', 'responds_to': 'vH'},
        {'name': 'partial'}, // missing fields degrade, never crash
      ],
    });
    expect(list, hasLength(2));
    expect(list.first.comments, 116);
    expect(list.first.respondsTo, 'vH');
    expect(list.last.comments, 0);
    expect(list.last.subject, isEmpty);
  });

  test('DigestRef.listFrom parses the daemon store index defensively', () {
    final list = DigestRef.listFrom({
      'store': '/s',
      'digests': [
        {'at': 101.0, 'responds_to': 'vidA', 'n_items': 2493, 'themes': 249,
         'verified': true, 'digest_sha256': 'abc'},
        {'responds_to': 'vidB'}, // missing fields degrade
      ],
    });
    expect(list, hasLength(2));
    expect(list.first.nItems, 2493);
    expect(list.first.verified, isTrue);
    expect(list.last.themes, 0);
    expect(list.last.verified, isFalse);
  });
}
