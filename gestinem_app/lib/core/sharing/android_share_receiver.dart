import 'dart:async';

import 'package:android_file_picker/android_file_picker.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../platform/android_integration.dart';

final androidShareReceiverProvider = Provider<AndroidShareReceiver>((ref) {
  final receiver = AndroidShareReceiver();
  ref.onDispose(receiver.dispose);
  return receiver;
});

class SharedContent {
  const SharedContent({required this.files, this.error});

  factory SharedContent.fromPlatformPayload(Object? payload) {
    if (payload is! Map) {
      return const SharedContent(
        files: [],
        error: 'Android no devolvio un archivo valido.',
      );
    }
    final files = <PlatformFile>[];
    final rawFiles = payload['files'];
    if (rawFiles is List) {
      for (final raw in rawFiles) {
        if (raw is! Map) continue;
        final path = raw['path']?.toString() ?? '';
        final name = raw['name']?.toString() ?? '';
        final size = raw['size'];
        if (path.isEmpty || name.isEmpty || size is! num || size < 0) continue;
        files.add(
          AndroidPlatformFile.fromMap({
            'name': name,
            'size': size.toInt(),
            'path': path,
          }),
        );
      }
    }
    return SharedContent(files: files, error: payload['error']?.toString());
  }

  final List<PlatformFile> files;
  final String? error;
}

class AndroidShareReceiver {
  final _events = StreamController<SharedContent>.broadcast();
  bool _initialized = false;

  Stream<SharedContent> get events => _events.stream;

  bool get supported =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  Future<void> initialize() async {
    if (!supported || _initialized) return;
    _initialized = true;
    androidIntegrationChannel.setMethodCallHandler((call) async {
      if (call.method == 'sharedContent') _emit(call.arguments);
    });
    try {
      final initial = await androidIntegrationChannel.invokeMethod<Object?>(
        'getInitialShare',
      );
      if (initial != null) _emit(initial);
    } on PlatformException catch (error) {
      _events.add(
        SharedContent(
          files: const [],
          error: error.message ?? 'No se pudo recibir el archivo compartido.',
        ),
      );
    }
  }

  void _emit(Object? payload) {
    final content = SharedContent.fromPlatformPayload(payload);
    if (content.files.isNotEmpty || (content.error?.isNotEmpty ?? false)) {
      _events.add(content);
    }
  }

  Future<void> discard(SharedContent content) async {
    if (!supported || content.files.isEmpty) return;
    try {
      await androidIntegrationChannel.invokeMethod<void>('discardShareFiles', {
        'paths': content.files
            .map((file) => file.path)
            .whereType<String>()
            .toList(),
      });
    } on PlatformException {
      // Son copias temporales en la cache de Android; el sistema tambien puede
      // eliminarlas y el siguiente uso limpia las antiguas.
    }
  }

  Future<bool> openMessageSoundSettings() async {
    if (!supported) return false;
    try {
      return await androidIntegrationChannel.invokeMethod<bool>(
            'openMessageSoundSettings',
          ) ??
          false;
    } on PlatformException {
      return false;
    }
  }

  Future<void> dispose() async {
    if (_initialized) {
      androidIntegrationChannel.setMethodCallHandler(null);
    }
    await _events.close();
  }
}
