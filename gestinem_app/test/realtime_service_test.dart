import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/core/websocket/realtime_service.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'test_helpers.dart';

class _CanalPrueba implements WebSocketChannel {
  final mensajes = StreamController<dynamic>();
  final preparado = Completer<void>();
  int cierres = 0;

  @override
  Stream<dynamic> get stream => mensajes.stream;

  @override
  Future<void> get ready => preparado.future;

  @override
  WebSocketSink get sink => _SalidaPrueba(this);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _SalidaPrueba implements WebSocketSink {
  _SalidaPrueba(this.canal);
  final _CanalPrueba canal;

  @override
  Future<void> close([int? closeCode, String? closeReason]) async {
    canal.cierres++;
    unawaited(canal.mensajes.close());
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _TicketPendiente extends JsonAdapter {
  _TicketPendiente() : super({'ticket': 'ticket-prueba'});
  final solicitado = Completer<void>();
  final responder = Completer<void>();

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    solicitado.complete();
    await responder.future;
    return super.fetch(options, requestStream, cancelFuture);
  }
}

ApiClient _api(JsonAdapter adapter) {
  final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
    ..httpClientAdapter = adapter;
  return ApiClient(dio: dio, tokenProvider: () => testSession.token);
}

void main() {
  test('socket silencioso se cierra y solicita una nueva conexion', () async {
    final canales = <_CanalPrueba>[];
    final reconectado = Completer<void>();
    final servicio = RealtimeService(
      plazoInactividad: const Duration(milliseconds: 30),
      crearCanal: (_) {
        final canal = _CanalPrueba()..preparado.complete();
        canales.add(canal);
        if (canales.length == 2) reconectado.complete();
        return canal;
      },
    );
    final eventos = <Map<String, dynamic>>[];
    final escucha = servicio.events.listen(eventos.add);
    final conexion = servicio.connect(
      testSession,
      _api(JsonAdapter({'ticket': 'ticket-prueba'})),
    );
    try {
      await reconectado.future.timeout(const Duration(seconds: 4));
      expect(canales.first.cierres, greaterThanOrEqualTo(1));
      expect(eventos.map((evento) => evento['type']), contains('disconnected'));
    } finally {
      await servicio.close();
      await conexion;
      await escucha.cancel();
    }
  });

  test('cerrar mientras se solicita ticket no abre un socket tardio', () async {
    final adapter = _TicketPendiente();
    var creados = 0;
    final servicio = RealtimeService(
      crearCanal: (_) {
        creados++;
        return _CanalPrueba();
      },
    );
    final conexion = servicio.connect(testSession, _api(adapter));
    await adapter.solicitado.future;
    await servicio.close();
    adapter.responder.complete();
    await conexion;
    expect(creados, 0);
  });

  test('cerrar durante la apertura no publica en un flujo cerrado', () async {
    final canal = _CanalPrueba();
    final creado = Completer<void>();
    final servicio = RealtimeService(
      crearCanal: (_) {
        creado.complete();
        return canal;
      },
    );
    final conexion = servicio.connect(
      testSession,
      _api(JsonAdapter({'ticket': 'ticket-prueba'})),
    );
    await creado.future;
    await servicio.close();
    canal.preparado.complete();
    await conexion;
    expect(canal.cierres, greaterThanOrEqualTo(1));
  });
}
