import 'dart:typed_data';

import 'archivo_descargado_stub.dart'
    if (dart.library.io) 'archivo_descargado_io.dart'
    if (dart.library.js_interop) 'archivo_descargado_web.dart'
    as implementation;

typedef AperturaArchivoDescargado = implementation.AperturaArchivoDescargado;

/// Reserva, durante la pulsacion del usuario, el contexto necesario para abrir
/// el archivo. En web evita que el navegador bloquee la pestana tras la
/// descarga asincrona; en aplicaciones nativas no realiza ninguna accion.
AperturaArchivoDescargado prepararAperturaArchivoDescargado() =>
    implementation.prepararAperturaArchivoDescargado();

Future<bool> abrirArchivoDescargado(
  AperturaArchivoDescargado apertura, {
  required Uri? uriGuardado,
  required Uint8List bytes,
  required String fileName,
  required String contentType,
}) => implementation.abrirArchivoDescargado(
  apertura,
  uriGuardado: uriGuardado,
  bytes: bytes,
  fileName: fileName,
  contentType: contentType,
);

void cancelarAperturaArchivoDescargado(AperturaArchivoDescargado apertura) =>
    implementation.cancelarAperturaArchivoDescargado(apertura);
