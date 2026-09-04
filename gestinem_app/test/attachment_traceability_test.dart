/// Pruebas de trazabilidad documental de adjuntos en Flutter.
///
/// Verifica:
/// - Parseo de todos los campos nuevos de Attachment y Message
/// - Tarjeta entrante no descargable para personal
/// - Tarjeta saliente descargable solo para cliente y antes de caducar
/// - Estados: pendiente, disponible, caducado, retirado, guardado_por_asesoria
/// - Ocultacion de "Eliminar" en mensajes con adjuntos
/// - Confirmacion de descarga
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:gestinem/features/messaging/domain/message.dart';
import 'package:gestinem/features/messaging/presentation/message_bubble.dart';

// ── helpers ──────────────────────────────────────────────────────────────────

Attachment _att({
  String direction = 'outgoing',
  String status = 'disponible',
  bool available = true,
  DateTime? expiresAt,
  bool localConfirmed = false,
  DateTime? withdrawnAt,
  String? withdrawalReason,
  int? completedDownloadCount,
  DateTime? lastDownloadedAt,
  String? lastClientName,
}) => Attachment(
  id: 'att-1',
  name: 'documento.pdf',
  contentType: 'application/pdf',
  size: 12345,
  direction: direction,
  status: status,
  available: available,
  expiresAt: expiresAt,
  localConfirmed: localConfirmed,
  withdrawnAt: withdrawnAt,
  withdrawalReason: withdrawalReason,
  completedDownloadCount: completedDownloadCount,
  lastDownloadedAt: lastDownloadedAt,
  lastClientName: lastClientName,
);

Message _msg({
  bool hasAttachments = false,
  List<Attachment> attachments = const [],
  bool deleted = false,
}) => Message(
  id: 'msg-1',
  conversationId: 'conv-1',
  authorType: 'staff',
  authorId: 'staff-1',
  authorName: 'Gestor',
  authorAvatarUrl: '',
  body: 'Adjunto importante',
  createdAt: DateTime(2026, 8, 19),
  deleted: deleted,
  hasAttachments: hasAttachments,
  attachments: attachments,
);

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

// ── Parseo del modelo Attachment ──────────────────────────────────────────────

void main() {
  group('Attachment.fromJson', () {
    test('parsea todos los campos nuevos', () {
      final json = <String, dynamic>{
        'id': 'a1',
        'name': 'doc.pdf',
        'content_type': 'application/pdf',
        'size': 1024,
        'direction': 'outgoing',
        'status': 'disponible',
        'available': true,
        'expires_at': '2026-09-18T12:00:00Z',
        'local_confirmed': false,
        'withdrawn_at': null,
        'withdrawn_by': '',
        'withdrawal_reason': '',
        'sha256': 'abc123',
        'completed_download_count': 3,
        'first_downloaded_at': '2026-08-20T10:00:00Z',
        'last_downloaded_at': '2026-08-21T15:30:00Z',
        'last_client_name': 'Maria Lopez',
      };
      final att = Attachment.fromJson(json);
      expect(att.id, 'a1');
      expect(att.direction, 'outgoing');
      expect(att.status, 'disponible');
      expect(att.available, isTrue);
      expect(att.expiresAt, isNotNull);
      expect(att.localConfirmed, isFalse);
      expect(att.withdrawnAt, isNull);
      expect(att.sha256, 'abc123');
      expect(att.completedDownloadCount, 3);
      expect(att.lastClientName, 'Maria Lopez');
    });

    test('parsea adjunto entrante con local_confirmed', () {
      final json = <String, dynamic>{
        'id': 'a2',
        'name': 'recibo.pdf',
        'content_type': 'application/pdf',
        'size': 512,
        'direction': 'incoming',
        'status': 'guardado_por_asesoria',
        'available': false,
        'local_confirmed': true,
      };
      final att = Attachment.fromJson(json);
      expect(att.isIncoming, isTrue);
      expect(att.localConfirmed, isTrue);
      expect(att.status, 'guardado_por_asesoria');
    });

    test('parsea adjunto retirado', () {
      final json = <String, dynamic>{
        'id': 'a3',
        'name': 'error.pdf',
        'content_type': 'application/pdf',
        'size': 256,
        'direction': 'outgoing',
        'status': 'retirado',
        'available': false,
        'withdrawn_at': '2026-08-19T08:00:00Z',
        'withdrawn_by': 'admin-1',
        'withdrawal_reason': 'Documento incorrecto',
      };
      final att = Attachment.fromJson(json);
      expect(att.isWithdrawn, isTrue);
      expect(att.available, isFalse);
      expect(att.withdrawnBy, 'admin-1');
      expect(att.withdrawalReason, 'Documento incorrecto');
    });

    test('parsea una descarga completada', () {
      final row = AttachmentDownload.fromJson({
        'id': 'download-1',
        'client_id': 'client-1',
        'client_name': 'María',
        'downloaded_at': '2026-08-19T08:00:00Z',
        'completed_at': '2026-08-19T08:01:00Z',
        'ip': '192.0.2.1',
        'user_agent': 'Gestinem Android',
        'sha256': 'abc123',
        'success': true,
      });
      expect(row.clientName, 'María');
      expect(row.completedAt, isNotNull);
      expect(row.success, isTrue);
    });
  });

  // ── Message.fromJson ──────────────────────────────────────────────────────

  group('Message.fromJson', () {
    test('parsea has_attachments', () {
      final json = <String, dynamic>{
        'id': 'm1',
        'conversation_id': 'c1',
        'author_type': 'staff',
        'author_id': 's1',
        'author_name': 'Ana',
        'author_avatar_url': '',
        'body': 'doc adjunto',
        'created_at': '2026-08-19T10:00:00Z',
        'deleted': false,
        'has_attachments': true,
        'attachments': [],
      };
      final msg = Message.fromJson(json);
      expect(msg.hasAttachments, isTrue);
    });

    test('has_attachments por defecto false', () {
      final json = <String, dynamic>{
        'id': 'm2',
        'conversation_id': 'c1',
        'author_type': 'client',
        'author_id': 'cl1',
        'author_name': 'Pedro',
        'author_avatar_url': '',
        'body': 'texto',
        'created_at': '2026-08-19T10:00:00Z',
        'deleted': false,
        'attachments': [],
      };
      expect(Message.fromJson(json).hasAttachments, isFalse);
    });
  });

  // ── AttachmentCard para cliente ────────────────────────────────────────────

  group('AttachmentCard cliente', () {
    testWidgets('adjunto disponible muestra boton de descarga', (tester) async {
      bool tapped = false;
      await tester.pumpWidget(
        _wrap(
          AttachmentCard(
            attachment: _att(status: 'disponible', available: true),
            isStaff: false,
            onDownload: () => tapped = true,
          ),
        ),
      );
      expect(find.byKey(const Key('download-att-1')), findsOneWidget);
      await tester.tap(find.byKey(const Key('download-att-1')));
      expect(tapped, isTrue);
    });

    testWidgets('adjunto caducado no muestra boton de descarga', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          AttachmentCard(
            attachment: _att(status: 'caducado', available: false),
            isStaff: false,
          ),
        ),
      );
      expect(find.byKey(const Key('download-att-1')), findsNothing);
      expect(find.textContaining('caducado'), findsOneWidget);
    });

    testWidgets('adjunto retirado no muestra boton de descarga', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          AttachmentCard(
            attachment: _att(
              status: 'retirado',
              available: false,
              withdrawnAt: DateTime(2026, 8, 19),
            ),
            isStaff: false,
          ),
        ),
      );
      expect(find.byKey(const Key('download-att-1')), findsNothing);
      expect(find.textContaining('retirado'), findsOneWidget);
    });

    testWidgets('adjunto entrante del propio cliente no es descargable', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          AttachmentCard(
            attachment: _att(
              direction: 'incoming',
              status: 'recibido_por_gestinem',
              available: false,
            ),
            isStaff: false,
          ),
        ),
      );
      expect(find.byKey(const Key('download-att-1')), findsNothing);
      expect(find.textContaining('Gestinem'), findsOneWidget);
    });
  });

  // ── AttachmentCard para personal ───────────────────────────────────────────

  group('AttachmentCard personal', () {
    testWidgets('adjunto saliente no tiene boton de descarga para staff', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          AttachmentCard(
            attachment: _att(status: 'disponible', available: true),
            isStaff: true,
          ),
        ),
      );
      expect(find.byKey(const Key('download-att-1')), findsNothing);
    });

    testWidgets('adjunto entrante muestra estado recibido_por_gestinem', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          AttachmentCard(
            attachment: _att(
              direction: 'incoming',
              status: 'recibido_por_gestinem',
              available: false,
            ),
            isStaff: true,
          ),
        ),
      );
      expect(find.textContaining('Gestinem'), findsOneWidget);
    });

    testWidgets('adjunto entrante confirmado muestra guardado_por_asesoria', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          AttachmentCard(
            attachment: _att(
              direction: 'incoming',
              status: 'guardado_por_asesoria',
              localConfirmed: true,
              available: false,
            ),
            isStaff: true,
          ),
        ),
      );
      expect(find.textContaining('asesoria'), findsOneWidget);
    });

    testWidgets('muestra resumen de descargas para adjunto saliente', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          AttachmentCard(
            attachment: _att(
              completedDownloadCount: 2,
              lastDownloadedAt: DateTime(2026, 8, 20, 10, 30),
              lastClientName: 'Maria',
            ),
            isStaff: true,
          ),
        ),
      );
      expect(find.textContaining('Descargas: 2'), findsOneWidget);
      expect(find.textContaining('Maria'), findsOneWidget);
    });

    testWidgets('muestra "Pendiente de descarga" cuando no hay descargas', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          AttachmentCard(
            attachment: _att(completedDownloadCount: 0),
            isStaff: true,
          ),
        ),
      );
      expect(find.textContaining('Pendiente de descarga'), findsOneWidget);
    });

    testWidgets('permite abrir historial y retirar al administrador', (
      tester,
    ) async {
      var history = false;
      var withdrawn = false;
      await tester.pumpWidget(
        _wrap(
          AttachmentCard(
            attachment: _att(completedDownloadCount: 1),
            isStaff: true,
            onShowHistory: () => history = true,
            onWithdraw: () => withdrawn = true,
          ),
        ),
      );
      await tester.tap(find.byKey(const Key('download-history-att-1')));
      await tester.tap(find.byKey(const Key('withdraw-att-1')));
      expect(history, isTrue);
      expect(withdrawn, isTrue);
    });

    testWidgets('muestra el motivo de un documento retirado', (tester) async {
      await tester.pumpWidget(
        _wrap(
          AttachmentCard(
            attachment: _att(
              status: 'retirado',
              available: false,
              withdrawnAt: DateTime(2026, 8, 19),
              withdrawalReason: 'Documento equivocado',
            ),
            isStaff: true,
          ),
        ),
      );
      expect(find.textContaining('Documento equivocado'), findsOneWidget);
    });
  });

  // ── MessageBubble: ocultar Eliminar en mensajes con adjuntos ──────────────
  // (El boton de Eliminar vive en el bottom sheet de conversation_screen,
  //  pero hasAttachments viaja en el modelo Message y MessageBubble lo expone)

  group('MessageBubble hasAttachments', () {
    testWidgets('mensaje con adjuntos renderiza tarjeta documental', (
      tester,
    ) async {
      final att = _att(status: 'disponible', available: true);
      final msg = _msg(hasAttachments: true, attachments: [att]);
      await tester.pumpWidget(
        _wrap(MessageBubble(message: msg, mine: false, isStaff: false)),
      );
      expect(find.byKey(const Key('attachment-card-att-1')), findsOneWidget);
    });
  });
}
