import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../platform/features_provider.dart';
import '../domain/certificate_request.dart';
import 'certificates_providers.dart';
import 'digital_certificate_card.dart';

class CertificatesScreen extends ConsumerStatefulWidget {
  const CertificatesScreen({super.key, this.companyCode, this.companyName});

  final String? companyCode;
  final String? companyName;

  bool get isStaffView => companyCode != null;

  @override
  ConsumerState<CertificatesScreen> createState() => _CertificatesScreenState();
}

class _CertificatesScreenState extends ConsumerState<CertificatesScreen> {
  String? _selectedType;
  final Map<String, String> _parameterValues = {};
  bool _submitting = false;
  final Set<String> _busyRequests = {};

  Future<void> _manageRequest(CertificateRequest item, String action) async {
    if (_busyRequests.contains(item.id)) return;
    if (action == 'remove') {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Eliminar solicitud'),
          content: Text(
            widget.isStaffView
                ? 'Se quitará de las solicitudes visibles del cliente y se podrá pedir otra hoy. '
                      'Se conservarán el historial y el PDF, si existe.'
                : 'Se quitará de Mis solicitudes y podrás pedir otra hoy. '
                      'El despacho conservará el historial y el PDF, si existe, '
                      'seguirá disponible en Mis documentos.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Volver'),
            ),
            FilledButton(
              key: const Key('confirm-remove-certificate-request'),
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Eliminar solicitud'),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted || _busyRequests.contains(item.id)) {
        return;
      }
    }
    if (!mounted) return;
    setState(() => _busyRequests.add(item.id));
    try {
      final repository = ref.read(certificatesRepositoryProvider);
      switch (action) {
        case 'remove':
          await repository.remove(item.id, companyCode: widget.companyCode);
        case 'retry':
          await repository.retry(item.id, companyCode: widget.companyCode);
        case 'cancel':
          await repository.cancel(item.id, companyCode: widget.companyCode);
        default:
          return;
      }
      _invalidateRequests();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(switch (action) {
              'remove' => 'Solicitud eliminada. Ya puedes pedir otra.',
              'retry' =>
                item.submittedAt != null
                    ? 'Consulta de emisión preparada. No se presentará otra solicitud.'
                    : 'Solicitud preparada para reintentar.',
              _ => 'Solicitud cancelada.',
            }),
          ),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    } finally {
      if (mounted) setState(() => _busyRequests.remove(item.id));
    }
  }

  Future<void> _requestCertificate() async {
    if (_selectedType == null || _submitting) return;
    setState(() => _submitting = true);
    try {
      await ref
          .read(certificatesRepositoryProvider)
          .create(
            _selectedType!,
            parameters: Map.of(_parameterValues),
            companyCode: widget.companyCode,
          );
      _invalidateRequests();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Solicitud registrada correctamente.')),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  void _refresh() {
    if (widget.companyCode case final companyCode?) {
      ref.invalidate(staffCertificateStatusProvider(companyCode));
      ref.invalidate(staffCertificateTypesProvider(companyCode));
      ref.invalidate(staffCertificateRequestsProvider(companyCode));
    } else {
      ref.invalidate(certificateStatusProvider);
      ref.invalidate(certificateTypesProvider);
      ref.invalidate(certificateRequestsProvider);
    }
  }

  void _invalidateRequests() {
    if (widget.companyCode case final companyCode?) {
      ref.invalidate(staffCertificateRequestsProvider(companyCode));
    } else {
      ref.invalidate(certificateRequestsProvider);
    }
  }

  @override
  Widget build(BuildContext context) {
    final features = widget.isStaffView
        ? null
        : ref.watch(platformFeaturesProvider).valueOrNull;
    if (!widget.isStaffView && features != null && !features.certificates) {
      return const Scaffold(
        body: Center(
          child: Text('La solicitud de certificados no está habilitada.'),
        ),
      );
    }
    final companyCode = widget.companyCode;
    final status = companyCode != null
        ? ref.watch(staffCertificateStatusProvider(companyCode))
        : ref.watch(certificateStatusProvider);
    final types = companyCode != null
        ? ref.watch(staffCertificateTypesProvider(companyCode))
        : ref.watch(certificateTypesProvider);
    final requests = companyCode != null
        ? ref.watch(staffCertificateRequestsProvider(companyCode))
        : ref.watch(certificateRequestsProvider);
    final configured =
        status.valueOrNull?.configured == true &&
        status.valueOrNull?.status == 'valid';

    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.companyName?.isNotEmpty == true
              ? 'Certificados · ${widget.companyName}'
              : 'Certificados oficiales',
        ),
        actions: [
          IconButton(onPressed: _refresh, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => _refresh(),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            DigitalCertificateCard(
              status: status,
              showContactOffice: !widget.isStaffView,
              onRefresh: _refresh,
            ),
            const SizedBox(height: 16),
            Text(
              'Nueva solicitud',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            types.when(
              data: (items) {
                final selected = items
                    .where((item) => item.code == _selectedType)
                    .firstOrNull;
                return Column(
                  children: [
                    DropdownButtonFormField<String>(
                      key: const Key('certificate-type-selector'),
                      isExpanded: true,
                      initialValue: _selectedType,
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        labelText: 'Tipo de certificado',
                      ),
                      items: items
                          .map(
                            (item) => DropdownMenuItem(
                              value: item.code,
                              child: Text(
                                '${item.organization} · ${item.name}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: configured
                          ? (value) => setState(() {
                              _selectedType = value;
                              _parameterValues.clear();
                            })
                          : null,
                    ),
                    if (selected != null)
                      ...selected.parameters.map(
                        (parameter) => Padding(
                          padding: const EdgeInsets.only(top: 12),
                          child: TextFormField(
                            key: Key('certificate-parameter-${parameter.key}'),
                            decoration: InputDecoration(
                              border: const OutlineInputBorder(),
                              labelText: parameter.label,
                              helperText: parameter.type == 'date'
                                  ? 'Formato: AAAA-MM-DD'
                                  : null,
                            ),
                            textCapitalization: parameter.type == 'tax_id'
                                ? TextCapitalization.characters
                                : TextCapitalization.words,
                            keyboardType: parameter.type == 'date'
                                ? TextInputType.datetime
                                : TextInputType.text,
                            onChanged: (value) => setState(
                              () => _parameterValues[parameter.key] = value
                                  .trim(),
                            ),
                          ),
                        ),
                      ),
                  ],
                );
              },
              loading: () => const LinearProgressIndicator(),
              error: (error, _) => Text(apiErrorMessage(error)),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              key: const Key('request-certificate-button'),
              onPressed:
                  configured &&
                      _selectedType != null &&
                      !_submitting &&
                      _requiredParametersComplete(types.valueOrNull ?? const [])
                  ? _requestCertificate
                  : null,
              icon: _submitting
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.verified_outlined),
              label: const Text('Solicitar certificado'),
            ),
            const SizedBox(height: 24),
            Text(
              widget.isStaffView
                  ? 'Solicitudes del cliente'
                  : 'Mis solicitudes',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            requests.when(
              data: (items) => items.isEmpty
                  ? const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(child: Text('Todavía no hay solicitudes.')),
                    )
                  : Column(children: items.map(_requestTile).toList()),
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => Text(apiErrorMessage(error)),
            ),
          ],
        ),
      ),
    );
  }

  bool _requiredParametersComplete(List<CertificateType> types) {
    final selected = types
        .where((item) => item.code == _selectedType)
        .firstOrNull;
    if (selected == null) return false;
    return selected.parameters
        .where((parameter) => parameter.required)
        .every(
          (parameter) => (_parameterValues[parameter.key] ?? '').isNotEmpty,
        );
  }

  Widget _requestTile(CertificateRequest item) {
    return Card(
      child: ListTile(
        title: Text(item.name),
        subtitle: Text(
          '${item.organization} · ${_statusLabel(item.status)}'
          '${item.certificateResult == 'POSITIVO'
              ? ' · Positivo'
              : item.certificateResult == 'NEGATIVO'
              ? ' · Negativo'
              : ''}'
          '${item.externalReference != null ? '\nReferencia: ${item.externalReference}' : ''}'
          '${item.status == 'awaiting_issuance' ? '\nResguardo recibido. Se comprobara la emision cada 24 horas.' : ''}'
          '${item.receiptDocumentId != null && !item.completed
              ? widget.isStaffView
                    ? '\nResguardo disponible en el área documental.'
                    : '\nToca para ver el documento de la solicitud.'
              : ''}'
          '${item.errorMessage?.isNotEmpty == true ? '\n${item.errorMessage}' : ''}',
        ),
        leading: Icon(_statusIcon(item.status)),
        trailing: _busyRequests.contains(item.id)
            ? const SizedBox.square(
                dimension: 24,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : item.removable || item.retryable
            ? PopupMenuButton<String>(
                key: Key('certificate-request-actions-${item.id}'),
                tooltip: 'Opciones de la solicitud',
                onSelected: (action) => _manageRequest(item, action),
                itemBuilder: (_) => [
                  if (item.retryable)
                    PopupMenuItem(
                      value: 'retry',
                      child: Text(
                        item.submittedAt != null
                            ? 'Comprobar emisión'
                            : 'Reintentar solicitud',
                      ),
                    ),
                  if (item.cancellable)
                    const PopupMenuItem(
                      value: 'cancel',
                      child: Text('Cancelar solicitud'),
                    ),
                  if (item.removable)
                    const PopupMenuItem(
                      value: 'remove',
                      child: Text('Eliminar solicitud'),
                    ),
                ],
              )
            : null,
        onTap:
            !widget.isStaffView &&
                (item.completed ? item.documentId : item.receiptDocumentId) !=
                    null
            ? () => context.push(
                '/documents/${item.completed ? item.documentId : item.receiptDocumentId}',
              )
            : null,
      ),
    );
  }

  static String _statusLabel(String status) => switch (status) {
    'queued' => 'Pendiente',
    'processing' => 'En tramitación',
    'completed' => 'Disponible',
    'awaiting_issuance' => 'Pendiente de emisión en Hacienda',
    'needs_action' => 'Requiere intervención',
    'failed' => 'No se pudo obtener',
    'cancelled' => 'Cancelada',
    _ => status,
  };

  static IconData _statusIcon(String status) => switch (status) {
    'completed' => Icons.check_circle_outline,
    'failed' => Icons.error_outline,
    'needs_action' => Icons.warning_amber_outlined,
    'processing' => Icons.sync,
    'cancelled' => Icons.cancel_outlined,
    _ => Icons.schedule,
  };
}
