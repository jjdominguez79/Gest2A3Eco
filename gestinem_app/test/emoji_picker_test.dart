import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/messaging/presentation/emoji_picker.dart';

void main() {
  test('inserta el emoticono en la posicion del cursor', () {
    final controller = TextEditingController(text: 'Hola mundo')
      ..selection = const TextSelection.collapsed(offset: 5);
    addTearDown(controller.dispose);

    insertarEmoji(controller, emoticonosChat.first);

    expect(controller.text, 'Hola ${emoticonosChat.first}mundo');
    expect(controller.selection.baseOffset, 5 + emoticonosChat.first.length);
  });

  test('sustituye la seleccion por el emoticono', () {
    final controller = TextEditingController(text: 'Hola mundo')
      ..selection = const TextSelection(baseOffset: 5, extentOffset: 10);
    addTearDown(controller.dispose);

    insertarEmoji(controller, emoticonosChat[1]);

    expect(controller.text, 'Hola ${emoticonosChat[1]}');
  });

  testWidgets('permite elegir varios emoticonos antes de cerrar', (
    tester,
  ) async {
    final controller = TextEditingController();
    final focusNode = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(focusNode.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              TextField(controller: controller, focusNode: focusNode),
              BotonSelectorEmoticonos(
                key: const Key('test-emoji-picker'),
                controller: controller,
                focusNode: focusNode,
              ),
            ],
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('test-emoji-picker')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('emoji-grid')), findsOneWidget);

    await tester.tap(find.byKey(const Key('emoji-option-0')));
    await tester.tap(find.byKey(const Key('emoji-option-1')));
    expect(
      controller.text,
      '${emoticonosChat[0]}${emoticonosChat[1]}',
    );

    await tester.tap(find.byKey(const Key('close-emoji-picker')));
    await tester.pumpAndSettle();
    expect(focusNode.hasFocus, isTrue);
  });
}
