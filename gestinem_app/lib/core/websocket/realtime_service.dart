import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/app_config.dart';
import '../api/api_client.dart';
import '../../features/auth/domain/user_profile.dart';

class RealtimeService {
  RealtimeService({
    WebSocketChannel Function(Uri)? crearCanal,
    Duration plazoInactividad = const Duration(seconds: 60),
  }) : _crearCanal = crearCanal ?? WebSocketChannel.connect,
       _plazoInactividad = plazoInactividad;

  final WebSocketChannel Function(Uri) _crearCanal;
  final Duration _plazoInactividad;
  final _events = StreamController<Map<String, dynamic>>.broadcast();
  WebSocketChannel? _channel;
  bool _closed = false;
  int _attempt = 0;

  Stream<Map<String, dynamic>> get events => _events.stream;

  Future<void> connect(AuthSession session, ApiClient api) async {
    if (_closed) return;
    final audience = session.profile.type.name;
    while (!_closed) {
      WebSocketChannel? channel;
      try {
        final response = await api.dio.post<Map<String, dynamic>>(
          '/$audience/ws-ticket',
        );
        if (_closed) break;
        final ticket = response.data!['ticket'] as String;
        final uri = Uri.parse(
          '${appConfig.webSocketUrl}/$audience',
        ).replace(queryParameters: {'ticket': ticket});
        channel = _crearCanal(uri);
        _channel = channel;
        await channel.ready.timeout(const Duration(seconds: 15));
        if (_closed) break;
        _attempt = 0;
        // El servidor envia ping cada 25 s, incluso con actividad en el chat.
        await for (final raw in channel.stream.timeout(_plazoInactividad)) {
          if (_closed) break;
          if (raw is String) {
            _events.add(jsonDecode(raw) as Map<String, dynamic>);
          }
        }
      } catch (_) {
        if (_closed) break;
      } finally {
        if (identical(_channel, channel)) _channel = null;
        if (channel != null) await _cerrarCanal(channel);
      }
      if (!_closed) {
        _events.add({'type': 'disconnected'});
        final seconds = min(30, pow(2, min(_attempt++, 5)).toInt());
        await Future<void>.delayed(Duration(seconds: seconds));
      }
    }
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    final channel = _channel;
    _channel = null;
    if (channel != null) await _cerrarCanal(channel);
    await _events.close();
  }

  Future<void> _cerrarCanal(WebSocketChannel channel) async {
    try {
      await channel.sink.close().timeout(const Duration(seconds: 3));
    } catch (_) {
      // Un socket sin red no debe impedir la reconexion ni cerrar la sesion.
    }
  }
}
