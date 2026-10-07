import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/messaging/domain/message.dart';
import 'package:gestinem/features/messaging/presentation/message_bubble.dart';

void main() {
  testWidgets('muestra estados propios y permite ocultarlos', (tester) async {
    final message = Message(
      id: 'receipt',
      conversationId: 'c1',
      authorType: 'staff',
      authorId: 's1',
      authorName: 'Ana',
      authorAvatarUrl: '',
      body: 'Aviso',
      createdAt: DateTime(2026),
      deleted: false,
      estadoEnvio: 'partially_read',
      lecturas: 1,
      destinatarios: 3,
    );
    Future<void> mostrar(bool mine, bool mostrarEstados) => tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            message: message,
            mine: mine,
            mostrarEstados: mostrarEstados,
          ),
        ),
      ),
    );
    await mostrar(true, true);
    expect(find.textContaining('Leido por algunos'), findsOneWidget);
    await mostrar(true, false);
    expect(find.textContaining('Leido por'), findsNothing);
    await mostrar(false, true);
    expect(find.textContaining('Leido por'), findsNothing);
  });

  testWidgets('identifica explicitamente el emisor propio y ajeno', (
    tester,
  ) async {
    final own = Message(
      id: 'mine',
      conversationId: 'c1',
      authorType: 'staff',
      authorId: 's1',
      authorName: 'Ana',
      authorAvatarUrl: '',
      body: 'Propio',
      createdAt: DateTime(2026),
      deleted: false,
    );
    final other = Message(
      id: 'other',
      conversationId: 'c1',
      authorType: 'staff',
      authorId: 's2',
      authorName: 'Bea',
      authorAvatarUrl: '',
      body: 'Ajeno',
      createdAt: DateTime(2026),
      deleted: false,
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              MessageBubble(message: own, mine: true),
              MessageBubble(message: other, mine: false),
            ],
          ),
        ),
      ),
    );

    expect(find.text('T\u00fa'), findsOneWidget);
    expect(find.text('Bea'), findsOneWidget);
  });

  testWidgets('renderiza referencia al mensaje respondido', (tester) async {
    final message = Message(
      id: 'm2',
      conversationId: 'c1',
      authorType: 'staff',
      authorId: 's1',
      authorName: 'Ana',
      authorAvatarUrl: '',
      body: 'Respuesta',
      createdAt: DateTime(2026),
      deleted: false,
      replyTo: const ReplyReference(
        id: 'm1',
        authorName: 'Maria',
        bodyFragment: 'Original',
        deleted: false,
      ),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: MessageBubble(message: message, mine: false)),
      ),
    );
    expect(find.byKey(const Key('reply-reference')), findsOneWidget);
    expect(find.text('Maria'), findsOneWidget);
    expect(find.text('Original'), findsOneWidget);
  });

  testWidgets('mensaje eliminado no revela el cuerpo', (tester) async {
    final message = Message(
      id: 'm3',
      conversationId: 'c1',
      authorType: 'staff',
      authorId: 's1',
      authorName: 'Ana',
      authorAvatarUrl: '',
      body: '',
      createdAt: DateTime(2026),
      deleted: true,
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: MessageBubble(message: message, mine: false)),
      ),
    );
    expect(find.byKey(const Key('deleted-message')), findsOneWidget);
    expect(find.text('Mensaje eliminado'), findsOneWidget);
  });

  testWidgets('aviso automatico se muestra centrado como mensaje de sistema', (
    tester,
  ) async {
    final message = Message(
      id: 'system-1',
      conversationId: 'c1',
      authorType: 'system',
      authorId: 'gestinem',
      authorName: 'Gestinem',
      authorAvatarUrl: '',
      body: 'Los cambios se han aplicado.',
      createdAt: DateTime(2026, 9, 29, 10, 10),
      deleted: false,
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: MessageBubble(message: message, mine: false)),
      ),
    );

    expect(find.text('Aviso de Gestinem'), findsOneWidget);
    expect(find.text('Los cambios se han aplicado.'), findsOneWidget);
    expect(find.byType(CircleAvatar), findsNothing);
  });

  testWidgets('muestra contacto estructurado y reacciones interactivas', (
    tester,
  ) async {
    String? selectedReaction;
    final message = Message(
      id: 'contact-1',
      conversationId: 'c1',
      authorType: 'client',
      authorId: 'client-1',
      authorName: 'Maria',
      authorAvatarUrl: '',
      body: 'Contacto compartido: Ana Garcia · 600123123',
      createdAt: DateTime(2026),
      deleted: false,
      sharedContacts: const [
        SharedContact(
          id: 'shared-1',
          name: 'Ana Garcia',
          organization: 'Ejemplo SL',
          phone: '600123123',
          email: 'ana@example.test',
        ),
      ],
      reactions: const [
        MessageReaction(
          emoji: '👍',
          count: 2,
          mine: true,
          names: ['Maria', 'Ana'],
        ),
      ],
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            message: message,
            mine: true,
            onReactionTap: (emoji) => selectedReaction = emoji,
          ),
        ),
      ),
    );

    expect(find.text('Ana Garcia'), findsOneWidget);
    expect(find.text('Ejemplo SL'), findsOneWidget);
    expect(find.text('600123123'), findsOneWidget);
    expect(find.text('ana@example.test'), findsOneWidget);
    expect(
      find.text('Contacto compartido: Ana Garcia · 600123123'),
      findsNothing,
    );
    expect(find.text('👍 2'), findsOneWidget);
    await tester.tap(find.text('👍 2'));
    expect(selectedReaction, '👍');
  });

  testWidgets('destaca claramente una mencion dirigida al usuario', (
    tester,
  ) async {
    final message = Message(
      id: 'mention-1',
      conversationId: 'group-1',
      authorType: 'staff',
      authorId: 'staff-1',
      authorName: 'Ana',
      authorAvatarUrl: '',
      body: '@Beatriz revisa este expediente',
      createdAt: DateTime(2026, 10, 7),
      deleted: false,
      mentions: const [
        MessageMention(staffId: 'staff-2', name: 'Beatriz', mine: true),
      ],
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: MessageBubble(message: message, mine: false)),
      ),
    );

    expect(find.byKey(const Key('mentions-mention-1')), findsOneWidget);
    expect(find.text('Para ti · @Beatriz'), findsOneWidget);
    final container = tester.widget<Container>(
      find.byKey(const Key('message-mention-1')),
    );
    expect((container.decoration! as BoxDecoration).border, isNotNull);
  });
}
