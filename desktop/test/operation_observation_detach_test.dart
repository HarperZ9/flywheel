import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_sse_decoder.dart';
import 'package:flywheel_desktop/controllers/operation_controller.dart';
import 'package:flywheel_desktop/models/operation_models.dart';

const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

OperationSnapshot _runningSnapshot() => OperationSnapshot.fromJson({
      'schema': operationSnapshotSchema,
      'operation_ref': _operation,
      'journey_ref': _journey,
      'event_head_sha256': _headA,
      'state': 'running',
      'can_cancel': true,
      'terminal_event_ref': null,
      'result_sha256': null,
    });
void main() {
  group('OperationController observation detach', () {
    test('awaits clean cancellation and closes only the local observer',
        () async {
      final cancelStarted = Completer<void>();
      final releaseCancel = Completer<void>();
      var cancelFinished = false;
      var interrupted = false;
      final running = _runningSnapshot();
      final stream = StreamController<GatewayOperationEvent>(
        onCancel: () async {
          cancelStarted.complete();
          await releaseCancel.future;
          cancelFinished = true;
        },
      );
      final controller = OperationController(requestId: () => 'stop-1');
      addTearDown(controller.dispose);
      addTearDown(stream.close);

      expect(controller.acceptSnapshot(running), isTrue);
      controller.observe(
        stream.stream,
        onProgress: (_) {},
        onInterrupted: () {
          interrupted = true;
        },
      );

      final detached = controller.detachObservation();
      await cancelStarted.future.timeout(const Duration(seconds: 1));
      expect(cancelFinished, isFalse);
      expect(controller.execution, same(running));

      releaseCancel.complete();
      expect(await detached.timeout(const Duration(seconds: 1)), isTrue);
      expect(cancelFinished, isTrue);
      expect(interrupted, isFalse);
      expect(controller.execution, same(running));
      expect(controller.observerState, OperationObserverState.closed);
    });

    test('failed cancellation returns false without leaking to the zone',
        () async {
      final uncaught = <Object>[];
      bool? detached;
      OperationController? controller;
      OperationSnapshot? running;
      var interrupted = false;

      await runZonedGuarded(() async {
        running = _runningSnapshot();
        final stream = StreamController<GatewayOperationEvent>(
          onCancel: () async {
            throw const GatewaySseException();
          },
        );
        addTearDown(stream.close);
        controller = OperationController(requestId: () => 'stop-1');
        addTearDown(controller!.dispose);
        expect(controller!.acceptSnapshot(running!), isTrue);
        controller!.observe(
          stream.stream,
          onProgress: (_) {},
          onInterrupted: () {
            interrupted = true;
          },
        );

        detached = await controller!
            .detachObservation()
            .timeout(const Duration(seconds: 1));
        await Future<void>.delayed(Duration.zero);
      }, (error, stackTrace) {
        uncaught.add(error);
      });

      expect(detached, isFalse);
      expect(uncaught.whereType<GatewaySseException>(), isEmpty);
      expect(interrupted, isFalse);
      expect(controller!.execution, same(running));
      expect(controller!.observerState, OperationObserverState.error);
    });

    test('never-completing cancellation times out as an unclean detach',
        () async {
      final stream = StreamController<GatewayOperationEvent>(
        onCancel: () => Completer<void>().future,
      );
      final controller = OperationController(
        requestId: () => 'stop-1',
        observationDetachTimeout: const Duration(milliseconds: 10),
      );
      final running = _runningSnapshot();
      var interrupted = false;
      addTearDown(controller.dispose);

      expect(controller.acceptSnapshot(running), isTrue);
      controller.observe(
        stream.stream,
        onProgress: (_) {},
        onInterrupted: () {
          interrupted = true;
        },
      );

      final detached = await controller
          .detachObservation()
          .timeout(const Duration(milliseconds: 250));

      expect(detached, isFalse);
      expect(interrupted, isFalse);
      expect(controller.execution, same(running));
      expect(controller.observerState, OperationObserverState.error);
    });

    test('late cancellation error after timeout stays handled', () async {
      final uncaught = <Object>[];
      bool? detached;
      OperationController? controller;
      OperationSnapshot? running;
      var interrupted = false;
      final releaseCancel = Completer<void>();

      await runZonedGuarded(() async {
        running = _runningSnapshot();
        final stream = StreamController<GatewayOperationEvent>(
          onCancel: () async {
            await releaseCancel.future;
            throw const GatewaySseException();
          },
        );
        addTearDown(stream.close);
        controller = OperationController(
          requestId: () => 'stop-1',
          observationDetachTimeout: const Duration(milliseconds: 10),
        );
        addTearDown(controller!.dispose);
        expect(controller!.acceptSnapshot(running!), isTrue);
        controller!.observe(
          stream.stream,
          onProgress: (_) {},
          onInterrupted: () {
            interrupted = true;
          },
        );

        detached = await controller!
            .detachObservation()
            .timeout(const Duration(milliseconds: 250));
        releaseCancel.complete();
        await Future<void>.delayed(const Duration(milliseconds: 50));
      }, (error, stackTrace) {
        uncaught.add(error);
      });

      expect(detached, isFalse);
      expect(uncaught.whereType<GatewaySseException>(), isEmpty);
      expect(interrupted, isFalse);
      expect(controller!.execution, same(running));
      expect(controller!.observerState, OperationObserverState.error);
    });

    test('dispose consumes cancellation failure without leaking to the zone',
        () async {
      final uncaught = <Object>[];

      await runZonedGuarded(() async {
        final stream = StreamController<GatewayOperationEvent>(
          onCancel: () async {
            throw const GatewaySseException();
          },
        );
        final controller = OperationController(requestId: () => 'stop-1');
        controller.observe(
          stream.stream,
          onProgress: (_) {},
          onInterrupted: () {},
        );

        controller.dispose();
        await Future<void>.delayed(const Duration(milliseconds: 50));
        await stream.close();
      }, (error, stackTrace) {
        uncaught.add(error);
      });

      expect(uncaught.whereType<GatewaySseException>(), isEmpty);
    });

    testWidgets(
        'dispose of a never-completing cancellation leaves no detach timer',
        (tester) async {
      final stream = StreamController<GatewayOperationEvent>(
        onCancel: () => Completer<void>().future,
      );
      final controller = OperationController(requestId: () => 'stop-1');
      controller.observe(
        stream.stream,
        onProgress: (_) {},
        onInterrupted: () {},
      );

      controller.dispose();
      await tester.pump();
    });

    test(
      'replacement observation consumes old cancellation failure without '
      'failing the new observer',
      () async {
        final uncaught = <Object>[];
        OperationController? controller;
        var interruptions = 0;

        await runZonedGuarded(() async {
          final oldStream = StreamController<GatewayOperationEvent>(
            onCancel: () async {
              await Future<void>.delayed(Duration.zero);
              throw const GatewaySseException();
            },
          );
          final newStream = StreamController<GatewayOperationEvent>();
          addTearDown(oldStream.close);
          addTearDown(newStream.close);
          controller = OperationController(requestId: () => 'stop-1');
          addTearDown(controller!.dispose);
          controller!.observe(
            oldStream.stream,
            onProgress: (_) {},
            onInterrupted: () {
              interruptions++;
            },
          );

          controller!.observe(
            newStream.stream,
            onProgress: (_) {},
            onInterrupted: () {
              interruptions++;
            },
          );
          await Future<void>.delayed(const Duration(milliseconds: 50));
        }, (error, stackTrace) {
          uncaught.add(error);
        });

        expect(uncaught.whereType<GatewaySseException>(), isEmpty);
        expect(interruptions, 0);
        expect(controller!.observerState, OperationObserverState.connecting);
      },
    );

    test('ordinary stream errors still fail the observer and interrupt',
        () async {
      final stream = StreamController<GatewayOperationEvent>();
      final controller = OperationController(requestId: () => 'stop-1');
      var interrupted = false;
      addTearDown(controller.dispose);
      addTearDown(stream.close);

      controller.observe(
        stream.stream,
        onProgress: (_) {},
        onInterrupted: () {
          interrupted = true;
        },
      );

      stream.addError(const GatewaySseException());
      await Future<void>.delayed(const Duration(milliseconds: 50));

      expect(interrupted, isTrue);
      expect(controller.observerState, OperationObserverState.error);
    });
  });
}
