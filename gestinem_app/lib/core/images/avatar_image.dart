import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as image;

const int avatarDimensionMaxima = 1024;
const int avatarTamanoOriginalMaximo = 30 * 1024 * 1024;

class AvatarImageException implements Exception {
  const AvatarImageException(this.message);

  final String message;

  @override
  String toString() => message;
}

Future<Uint8List> prepararAvatar(PlatformFile archivo) async {
  final original = await archivo.readAsBytes();
  if (original.lengthInBytes > avatarTamanoOriginalMaximo) {
    throw const AvatarImageException(
      'La imagen es demasiado grande. Selecciona una foto de menos de 30 MB.',
    );
  }
  return compute(normalizarAvatar, original);
}

/// Aplica la orientacion EXIF y genera un JPEG ligero para enviarlo al backend.
Uint8List normalizarAvatar(Uint8List original) {
  image.Image? decodificada;
  try {
    decodificada = image.decodeImage(original);
  } on RangeError {
    throw const AvatarImageException(
      'El archivo seleccionado no es una imagen valida.',
    );
  } on FormatException {
    throw const AvatarImageException(
      'El archivo seleccionado no es una imagen valida.',
    );
  }
  if (decodificada == null) {
    throw const AvatarImageException(
      'El archivo seleccionado no es una imagen valida.',
    );
  }

  final orientada = image.bakeOrientation(decodificada);
  final ladoMayor = orientada.width > orientada.height
      ? orientada.width
      : orientada.height;
  final preparada = ladoMayor > avatarDimensionMaxima
      ? image.copyResize(
          orientada,
          width: orientada.width >= orientada.height
              ? avatarDimensionMaxima
              : null,
          height: orientada.height > orientada.width
              ? avatarDimensionMaxima
              : null,
          interpolation: image.Interpolation.average,
        )
      : orientada;

  return Uint8List.fromList(image.encodeJpg(preparada, quality: 85));
}
