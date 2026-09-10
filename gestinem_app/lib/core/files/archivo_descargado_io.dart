import 'dart:io';
import 'dart:typed_data';

import 'package:open_filex/open_filex.dart';

final class AperturaArchivoDescargado {
  const AperturaArchivoDescargado();
}

AperturaArchivoDescargado prepararAperturaArchivoDescargado() =>
    const AperturaArchivoDescargado();

Future<bool> abrirArchivoDescargado(
  AperturaArchivoDescargado apertura, {
  required Uri? uriGuardado,
  required Uint8List bytes,
  required String fileName,
  required String contentType,
}) async {
  try {
    var ruta = uriGuardado?.scheme == 'file' ? uriGuardado!.toFilePath() : '';
    if (ruta.isEmpty) {
      final nombreSeguro = fileName
          .replaceAll(RegExp(r'[<>:"/\\|?*\x00-\x1F]'), '_')
          .trim();
      final temporal = File(
        '${Directory.systemTemp.path}${Platform.pathSeparator}'
        'gestinem_${DateTime.now().microsecondsSinceEpoch}_'
        '${nombreSeguro.isEmpty ? 'adjunto' : nombreSeguro}',
      );
      await temporal.writeAsBytes(bytes, flush: true);
      ruta = temporal.path;
    }
    final resultado = await OpenFilex.open(ruta, type: contentType);
    return resultado.type == ResultType.done;
  } catch (_) {
    return false;
  }
}

void cancelarAperturaArchivoDescargado(AperturaArchivoDescargado apertura) {}
