import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/images/avatar_image.dart';
import 'package:image/image.dart' as image;

void main() {
  test('reduce una foto grande y la convierte en JPEG', () {
    final original = image.Image(width: 2400, height: 1600);
    image.fill(original, color: image.ColorRgb8(20, 90, 134));

    final resultado = normalizarAvatar(
      Uint8List.fromList(image.encodePng(original)),
    );
    final avatar = image.decodeJpg(resultado);

    expect(avatar, isNotNull);
    expect(avatar!.width, avatarDimensionMaxima);
    expect(avatar.height, lessThanOrEqualTo(avatarDimensionMaxima));
    expect(resultado.lengthInBytes, lessThan(5 * 1024 * 1024));
  });

  test('rechaza un archivo que no contiene una imagen', () {
    expect(
      () => normalizarAvatar(Uint8List.fromList([1, 2, 3, 4])),
      throwsA(isA<AvatarImageException>()),
    );
  });
}
