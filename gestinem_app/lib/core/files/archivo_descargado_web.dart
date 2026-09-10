import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

final class AperturaArchivoDescargado {
  AperturaArchivoDescargado(this.ventana);

  final web.Window? ventana;
}

AperturaArchivoDescargado prepararAperturaArchivoDescargado() =>
    AperturaArchivoDescargado(web.window.open('', '_blank'));

Future<bool> abrirArchivoDescargado(
  AperturaArchivoDescargado apertura, {
  required Uri? uriGuardado,
  required Uint8List bytes,
  required String fileName,
  required String contentType,
}) async {
  try {
    final blob = web.Blob(
      [bytes.toJS].toJS,
      web.BlobPropertyBag(type: contentType),
    );
    final url = web.URL.createObjectURL(blob);
    final ventana = apertura.ventana ?? web.window.open(url, '_blank');
    if (ventana == null) {
      web.URL.revokeObjectURL(url);
      return false;
    }
    if (apertura.ventana != null) ventana.location.href = url;
    Future<void>.delayed(
      const Duration(minutes: 1),
      () => web.URL.revokeObjectURL(url),
    );
    return true;
  } catch (_) {
    apertura.ventana?.close();
    return false;
  }
}

void cancelarAperturaArchivoDescargado(AperturaArchivoDescargado apertura) {
  apertura.ventana?.close();
}
