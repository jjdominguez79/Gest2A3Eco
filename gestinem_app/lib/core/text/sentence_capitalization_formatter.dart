import 'package:flutter/services.dart';

/// Aplica mayuscula a la primera letra del texto y de cada frase.
///
/// Se considera una nueva frase despues de `.`, `!`, `?` o un salto de linea.
/// Tras un signo de cierre se exige un espacio para no alterar dominios, correos
/// o numeros decimales escritos dentro del mensaje.
class SentenceCapitalizationFormatter extends TextInputFormatter {
  const SentenceCapitalizationFormatter();

  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    if (newValue.composing.isValid && !newValue.composing.isCollapsed) {
      return newValue;
    }
    final formatted = capitalizeSentenceStarts(newValue.text);
    if (formatted == newValue.text) return newValue;
    return newValue.copyWith(text: formatted);
  }
}

String capitalizeSentenceStarts(String text) {
  if (text.isEmpty) return text;
  final output = StringBuffer();
  var capitalizeNext = true;
  var afterTerminator = false;

  for (var index = 0; index < text.length; index++) {
    final character = text[index];

    if (character == '\n' || character == '\r') {
      output.write(character);
      capitalizeNext = true;
      afterTerminator = false;
      continue;
    }

    if (afterTerminator) {
      if (_isHorizontalWhitespace(character)) {
        capitalizeNext = true;
      } else if (!_isOpeningMark(character)) {
        afterTerminator = false;
      }
    }

    if (capitalizeNext && !_isSkippableBeforeSentence(character)) {
      final upper = character.toUpperCase();
      // Mantener offsets de seleccion/composicion incluso para caracteres cuya
      // mayuscula Unicode ocupe mas unidades UTF-16.
      output.write(upper.length == character.length ? upper : character);
      capitalizeNext = false;
    } else {
      output.write(character);
    }

    if (_isTerminator(character)) {
      afterTerminator = true;
    }
  }
  return output.toString();
}

bool _isTerminator(String character) => '.!?'.contains(character);

bool _isHorizontalWhitespace(String character) =>
    character == ' ' || character == '\t';

bool _isOpeningMark(String character) => const [
  '"',
  "'",
  '\u00bf',
  '\u00a1',
  '(',
  '[',
  '{',
  '\u00ab',
  '\u201c',
  '\u2018',
].contains(character);

bool _isSkippableBeforeSentence(String character) =>
    _isHorizontalWhitespace(character) || _isOpeningMark(character);
