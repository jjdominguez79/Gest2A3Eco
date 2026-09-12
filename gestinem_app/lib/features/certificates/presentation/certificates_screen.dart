import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../platform/features_provider.dart';
import '../domain/certificate_request.dart';
import 'certificates_providers.dart';

class CertificatesScreen extends ConsumerStatefulWidget {
  const CertificatesScreen({super.key});

  @override
  ConsumerState<CertificatesScreen> createState() => _CertificatesScreenState();
}

class _CertificatesScreenState extends ConsumerState<CertificatesScreen> {
  String? _selectedType;
  final Map<String, String> _parameterValues = {};
  bool _submitting = false;

  Future<void> _requestCertificate() async {
    if (_selectedType == null || _submitting) return;
    setState(() => _submitting = true);
    try {
      await ref
          .read(certificatesRepositoryProvider)
          .create(_selectedType!, parameters: Map.of(_parameterValues));
      ref.invalidate(certificateRequestsProvider);
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
    ref.invalidate(certificateStatusProvider);
    ref.invalidate(certificateTypesProvider);
    ref.invalidate(certificateRequestsProvider);
  }

  @override
  Widget build(BuildContext context) {
    final features = ref.watch(platformFeaturesProvider).valueOrNull;
    if (features != null && !features.certificates) {
      return const Scaffold(
        body: Center(
          child: Text('La solicitud de certificados no está habilitada.'),
        ),
      );
    }
    final status = ref.watch(certificateStatusProvider);
    final types = ref.watch(certificateTypesProvider);
    final requests = ref.watch(certificateRequestsProvider);
    final configured =
        status.valueOrNull?.configured == true &&
        status.valueOrNull?.status == 'valid';

    return Scaffold(
      appBar: AppBar(
        title: const Text('Certificados oficiales'),
        actions: [
          IconButton(onPressed: _refresh, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => _refresh(),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _CertificateStatusCard(status: status),
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
              'Mis solicitudes',
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
          '${item.errorMessage?.isNotEmpty == true ? '\n${item.errorMessage}' : ''}',
        ),
        leading: Icon(_statusIcon(item.status)),
        trailing: item.completed && item.documentId != null
            ? const Icon(Icons.chevron_right)
            : item.cancellable
            ? IconButton(
                tooltip: 'Cancelar solicitud',
                icon: const Icon(Icons.cancel_outlined),
                onPressed: () async {
                  await ref
                      .read(certificatesRepositoryProvider)
                      .cancel(item.id);
                  ref.invalidate(certificateRequestsProvider);
                },
              )
            : null,
        onTap: item.completed && item.documentId != null
            ? () => context.push('/documents/${item.documentId}')
            : null,
      ),
    );
  }

  static String _statusLabel(String status) => switch (status) {
    'queued' => 'Pendiente',
    'processing' => 'En tramitación',
    'completed' => 'Disponible',
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

class _CertificateStatusCard extends StatelessWidget {
  const _CertificateStatusCard({required this.status});

  final AsyncValue<CertificateStatus> status;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: status.when(
          data: (value) {
            final valid = value.configured && value.status == 'valid';
            return Row(
              children: [
                Icon(valid ? Icons.lock_outline : Icons.warning_amber_outlined),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    valid
                        ? 'Certificado digital preparado${value.validUntil == null ? '' : ' hasta ${value.validUntil!.day}/${value.validUntil!.month}/${value.validUntil!.year}'}.'
                        : value.status == 'expired'
                        ? 'El certificado digital está caducado.'
                        : 'El despacho todavía no ha preparado tu certificado digital.',
                  ),
                ),
              ],
            );
          },
          loading: () => const LinearProgressIndicator(),
          error: (error, _) => Text(apiErrorMessage(error)),
        ),
      ),
    );
  }
}
