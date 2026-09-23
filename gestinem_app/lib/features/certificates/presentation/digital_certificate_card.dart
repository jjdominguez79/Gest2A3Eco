import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../domain/certificate_request.dart';
import '../../messaging/presentation/messaging_providers.dart';
import 'certificates_providers.dart';

class DigitalCertificateCard extends ConsumerStatefulWidget {
  const DigitalCertificateCard({
    super.key,
    required this.status,
    this.showContactOffice = true,
    this.onRefresh,
  });

  final AsyncValue<CertificateStatus> status;
  final bool showContactOffice;
  final VoidCallback? onRefresh;

  @override
  ConsumerState<DigitalCertificateCard> createState() =>
      _DigitalCertificateCardState();
}

class _DigitalCertificateCardState
    extends ConsumerState<DigitalCertificateCard> {
  bool _openingConversation = false;

  Future<void> _contactOffice(CertificateStatus status) async {
    if (_openingConversation) return;
    setState(() => _openingConversation = true);
    try {
      final conversations = await ref.read(conversationsProvider.future);
      if (conversations.isEmpty) {
        throw StateError('No hay una conversación disponible con el despacho.');
      }
      final target = conversations.firstWhere(
        (item) => item.kind == 'fiscal',
        orElse: () => conversations.first,
      );
      if (!mounted) return;
      final draft = switch (status.status) {
        'missing' =>
          'Hola, en mi área de cliente no consta un certificado digital preparado por el despacho. ¿Podéis indicarme cómo incorporarlo para solicitar certificados oficiales?',
        'expired' =>
          'Hola, el certificado digital preparado por el despacho figura caducado. ¿Podéis indicarme cómo renovarlo?',
        _ =>
          'Hola, quisiera consultar el estado y la renovación de mi certificado digital preparado por el despacho.',
      };
      context.push('/conversation/${target.id}', extra: draft);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              error is StateError ? error.message : apiErrorMessage(error),
            ),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _openingConversation = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: widget.status.when(
          loading: () => const LinearProgressIndicator(),
          error: (error, _) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'No se pudo consultar el certificado: ${apiErrorMessage(error)}',
              ),
              TextButton.icon(
                onPressed:
                    widget.onRefresh ??
                    () => ref.invalidate(certificateStatusProvider),
                icon: const Icon(Icons.refresh),
                label: const Text('Reintentar'),
              ),
            ],
          ),
          data: (value) {
            final daysLeft = value.validUntil
                ?.difference(DateTime.now())
                .inDays;
            final expiringSoon =
                value.status == 'valid' &&
                daysLeft != null &&
                daysLeft >= 0 &&
                daysLeft <= 30;
            final title = switch (value.status) {
              'expired' => 'Certificado digital caducado',
              'not_yet_valid' => 'Certificado digital aún no vigente',
              'valid' when expiringSoon =>
                'Certificado digital próximo a vencer',
              'valid' => 'Certificado digital en vigor',
              _ => 'Certificado digital no preparado',
            };
            final needsOffice = value.status != 'valid' || expiringSoon;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      value.status == 'valid' && !expiringSoon
                          ? Icons.verified_user_outlined
                          : Icons.warning_amber_outlined,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        title,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                if (!value.configured)
                  const Text(
                    'No consta un certificado digital preparado por el despacho.',
                  ),
                if (value.configured) ...[
                  if (value.commonName?.isNotEmpty == true)
                    Text('Titular: ${value.commonName}'),
                  if (value.issuer?.isNotEmpty == true)
                    Text('Emisor: ${value.issuer}'),
                  if (value.validFrom != null)
                    Text('Válido desde: ${_date(value.validFrom!)}'),
                  if (value.validUntil != null)
                    Text('Vence: ${_date(value.validUntil!)}'),
                ],
                const SizedBox(height: 8),
                const Text(
                  'El certificado permanece custodiado por el despacho. Aquí solo se muestran sus datos.',
                ),
                if (value.configured && value.status == 'valid')
                  const Text(
                    'Estado calculado según las fechas del certificado.',
                  ),
                if (needsOffice && widget.showContactOffice) ...[
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    key: const Key('digital-certificate-contact-office'),
                    onPressed: _openingConversation
                        ? null
                        : () => _contactOffice(value),
                    icon: const Icon(Icons.chat_outlined),
                    label: Text(
                      value.status == 'missing'
                          ? 'Pedir incorporación al despacho'
                          : 'Consultar al despacho',
                    ),
                  ),
                ],
              ],
            );
          },
        ),
      ),
    );
  }

  String _date(DateTime value) {
    final local = value.toLocal();
    return '${local.day.toString().padLeft(2, '0')}/${local.month.toString().padLeft(2, '0')}/${local.year}';
  }
}
