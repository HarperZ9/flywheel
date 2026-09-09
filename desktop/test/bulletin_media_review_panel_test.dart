import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/bulletin_media_models.dart';
import 'package:flywheel_desktop/widgets/bulletin_media_review_panel.dart';

import 'bulletin_media_test_support.dart';
import 'bulletin_media_widget_test_support.dart';

void main() {
  testWidgets('review panel puts public content before secondary hashes',
      (tester) async {
    final file = File('${Directory.systemTemp.path}/bulletin-panel.png')
      ..writeAsBytesSync(tinyPngBytes());
    final review = BulletinMediaReview.fromJson(reviewJson());

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: BulletinMediaReviewPanel(
          review: review,
          loader: TestMediaLoader(file),
          mediaPlayerBuilder: (_, __) => const Text('Native player'),
        ),
      ),
    ));

    expect(find.text('The final public post body.'), findsOneWidget);
    expect(find.text('One pixel meme preview.'), findsOneWidget);
    expect(find.textContaining('entire selected file becomes public'),
        findsOneWidget);
    final bodyTop = tester.getTopLeft(find.text('The final public post body.'));
    final detailsTop =
        tester.getTopLeft(find.text('Secondary verification details'));
    expect(bodyTop.dy, lessThan(detailsTop.dy));
    expect(find.textContaining('C:/Users'), findsNothing);
    file.deleteSync();
  });

  testWidgets('panel loads exact audio/video bytes into native player slots',
      (tester) async {
    final file = File('${Directory.systemTemp.path}/bulletin-panel.bin')
      ..writeAsBytesSync(tinyPngBytes());
    final review = BulletinMediaReview.fromJson(
        reviewJson(kind: 'audio', mediaType: 'audio/wav'));
    String? playedKind;

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: BulletinMediaReviewPanel(
          review: review,
          loader: TestMediaLoader(file),
          mediaPlayerBuilder: (_, media) {
            playedKind = media.attachment.kind.name;
            return Text('Native player: $playedKind');
          },
        ),
      ),
    ));

    await tester.tap(find.text('Load media preview'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(playedKind, 'audio');
    expect(find.text('Native player: audio'), findsOneWidget);
    file.deleteSync();
  });

  testWidgets('review change deletes previously loaded preview bytes',
      (tester) async {
    final first = File('${Directory.systemTemp.path}/bulletin-panel-first.png')
      ..writeAsBytesSync(tinyPngBytes());
    final second =
        File('${Directory.systemTemp.path}/bulletin-panel-second.png')
          ..writeAsBytesSync(tinyPngBytes());
    addTearDown(() {
      if (first.existsSync()) first.deleteSync();
      if (second.existsSync()) second.deleteSync();
    });

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: BulletinMediaReviewPanel(
            review: BulletinMediaReview.fromJson(reviewJson()),
            loader: TestMediaLoader(first),
            mediaPlayerBuilder: (_, __) => const Text('Native player'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('Load media preview'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(first.existsSync(), isTrue);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: BulletinMediaReviewPanel(
            review: BulletinMediaReview.fromJson(reviewJson(
                attachmentSha: shaB, extra: {'preview_sha256': shaB})),
            loader: TestMediaLoader(second),
            mediaPlayerBuilder: (_, __) => const Text('Native player'),
          ),
        ),
      ),
    ));
    await tester.pump();

    expect(first.existsSync(), isFalse);
    expect(find.text('Load media preview'), findsOneWidget);
  });
}
