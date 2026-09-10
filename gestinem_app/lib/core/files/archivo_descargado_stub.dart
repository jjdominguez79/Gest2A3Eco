import 'dart:typed_data';

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
}) async => false;

void cancelarAperturaArchivoDescargado(AperturaArchivoDescargado apertura) {}
