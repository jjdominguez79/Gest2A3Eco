import 'dart:io';

Future<void> finishExternalAuthHandoff() async {
  if (Platform.isWindows) {
    // El callback del protocolo abre otra instancia con el codigo de Microsoft.
    // Cerramos la instancia que inicio el navegador para no dejarla esperando.
    exit(0);
  }
}
