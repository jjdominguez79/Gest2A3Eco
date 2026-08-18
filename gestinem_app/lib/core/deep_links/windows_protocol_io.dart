import 'dart:io';

import 'package:flutter/foundation.dart';

Future<void> registerWindowsProtocol() async {
  if (!Platform.isWindows) return;
  const root = r'HKCU\Software\Classes\es.gestinem.app';
  final command = '"${Platform.resolvedExecutable}" "%1"';
  try {
    await _regAdd(root, null, 'URL:Gestinem');
    await _regAdd(root, 'URL Protocol', '');
    await _regAdd('$root\\shell\\open\\command', null, command);
  } catch (error) {
    debugPrint('No se pudo registrar el protocolo de Gestinem: $error');
  }
}

Future<void> _regAdd(String key, String? name, String value) async {
  final arguments = <String>['add', key];
  if (name == null) {
    arguments.add('/ve');
  } else {
    arguments.addAll(['/v', name]);
  }
  arguments.addAll(['/t', 'REG_SZ', '/d', value, '/f']);
  final result = await Process.run('reg.exe', arguments);
  if (result.exitCode != 0) {
    throw ProcessException(
      'reg.exe',
      arguments,
      result.stderr.toString(),
      result.exitCode,
    );
  }
}
