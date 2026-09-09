import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/text/sentence_capitalization_formatter.dart';

void main() {
  const formatter = SentenceCapitalizationFormatter();

  test('pone en mayuscula el inicio y las frases posteriores', () {
    expect(
      capitalizeSentenceStarts('hola. esto sigue! otra? fin'),
      'Hola. Esto sigue! Otra? Fin',
    );
    expect(
      capitalizeSentenceStarts('  ¿que tal? "muy bien"'),
      '  ¿Que tal? "Muy bien"',
    );
    expect(capitalizeSentenceStarts('uno\ndos'), 'Uno\nDos');
  });

  test('no altera dominios, correos ni decimales', () {
    expect(
      capitalizeSentenceStarts('visita app.gestinem.es o escribe a@b.es. fin'),
      'Visita app.gestinem.es o escribe a@b.es. Fin',
    );
    expect(capitalizeSentenceStarts('importe 3.14. fin'), 'Importe 3.14. Fin');
  });

  test('conserva la seleccion del editor', () {
    const value = TextEditingValue(
      text: 'hola. adios',
      selection: TextSelection.collapsed(offset: 12),
    );
    final result = formatter.formatEditUpdate(TextEditingValue.empty, value);
    expect(result.text, 'Hola. Adios');
    expect(result.selection, value.selection);
  });

  test('no interfiere mientras el teclado esta componiendo', () {
    const value = TextEditingValue(
      text: 'hola',
      selection: TextSelection.collapsed(offset: 4),
      composing: TextRange(start: 0, end: 4),
    );
    expect(formatter.formatEditUpdate(TextEditingValue.empty, value), value);
  });
}
