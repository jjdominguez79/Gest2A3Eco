import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/messaging/domain/message.dart';
import 'package:gestinem/features/messaging/presentation/message_bubble.dart';

void main() {
  testWidgets('identifica explicitamente el emisor propio y ajeno', (tester) async {
    final own = Message(
      id: 'mine', conversationId: 'c1', authorType: 'staff', authorId: 's1',
      authorName: 'Ana', authorAvatarUrl: '', body: 'Propio',
      createdAt: DateTime(2026), deleted: false,
    );
    final other = Message(
      id: 'other', conversationId: 'c1', authorType: 'staff', authorId: 's2',
      authorName: 'Bea', authorAvatarUrl: '', body: 'Ajeno',
      createdAt: DateTime(2026), deleted: false,
    );
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: Column(children: [
      MessageBubble(message: own, mine: true),
      MessageBubble(message: other, mine: false),
    ]))));

    expect(find.text('T\u00fa'), findsOneWidget);
    expect(find.text('Bea'), findsOneWidget);
  });

  testWidgets('renderiza referencia al mensaje respondido', (tester) async {
    final message = Message(
      id: 'm2', conversationId: 'c1', authorType: 'staff', authorId: 's1',
      authorName: 'Ana', authorAvatarUrl: '', body: 'Respuesta', createdAt: DateTime(2026), deleted: false,
      replyTo: const ReplyReference(id: 'm1', authorName: 'Maria', bodyFragment: 'Original', deleted: false),
    );
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: MessageBubble(message: message, mine: false))));
    expect(find.byKey(const Key('reply-reference')), findsOneWidget);
    expect(find.text('Maria'), findsOneWidget);
    expect(find.text('Original'), findsOneWidget);
  });

  testWidgets('mensaje eliminado no revela el cuerpo', (tester) async {
    final message = Message(
      id: 'm3', conversationId: 'c1', authorType: 'staff', authorId: 's1',
      authorName: 'Ana', authorAvatarUrl: '', body: '', createdAt: DateTime(2026), deleted: true,
    );
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: MessageBubble(message: message, mine: false))));
    expect(find.byKey(const Key('deleted-message')), findsOneWidget);
    expect(find.text('Mensaje eliminado'), findsOneWidget);
  });
}
