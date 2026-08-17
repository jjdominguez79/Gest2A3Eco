import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/app_config.dart';
import '../api/api_client.dart';
import '../../features/auth/domain/user_profile.dart';

class RealtimeService {
  final _events = StreamController<Map<String, dynamic>>.broadcast();
  WebSocketChannel? _channel;
  bool _closed = false;
  int _attempt = 0;

  Stream<Map<String, dynamic>> get events => _events.stream;

  Future<void> connect(AuthSession session, ApiClient api) async {
    _closed = false;
    final audience = session.profile.type.name;
    while (!_closed) {
      try {
        final response = await api.dio.post<Map<String, dynamic>>('/$audience/ws-ticket');
        final ticket = response.data!['ticket'] as String;
        final uri = Uri.parse('${appConfig.webSocketUrl}/$audience').replace(
          queryParameters: {'ticket': ticket},
        );
        final channel = WebSocketChannel.connect(uri);
        _channel = channel;
        await channel.ready;
        _attempt = 0;
        await for (final raw in channel.stream) {
          if (raw is String) {
            _events.add(jsonDecode(raw) as Map<String, dynamic>);
          }
        }
      } catch (_) {
        if (_closed) break;
      }
      if (!_closed) {
        final seconds = min(30, pow(2, min(_attempt++, 5)).toInt());
        await Future<void>.delayed(Duration(seconds: seconds));
      }
    }
  }

  Future<void> close() async {
    _closed = true;
    await _channel?.sink.close();
    await _events.close();
  }
}
