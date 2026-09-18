import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../platform/features_provider.dart';

/// Menu documental del cliente, sin alterar las habilitaciones del despacho.
class DocumentationScreen extends ConsumerWidget {
  const DocumentationScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final funciones = ref.watch(platformFeaturesProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Documentaci\u00f3n'),
        leading: BackButton(
          key: const Key('documentation-back'),
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              // Tambien permitir volver al abrir un enlace directo.
              context.go('/');
            }
          },
        ),
      ),
      body: funciones.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('No se pudo consultar la disponibilidad.'),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: () => ref.invalidate(platformFeaturesProvider),
                icon: const Icon(Icons.refresh),
                label: const Text('Reintentar'),
              ),
            ],
          ),
        ),
        data: (funciones) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text(
              'Consulta tus documentos y solicita certificados oficiales al despacho.',
            ),
            const SizedBox(height: 16),
            Card(
              child: ListTile(
                key: const Key('documentation-documents'),
                leading: const Icon(Icons.folder_outlined),
                title: const Text('Mis documentos'),
                subtitle: Text(
                  funciones.documents
                      ? 'Facturas, certificados, n\u00f3minas, impuestos y otros documentos.'
                      : 'El despacho todav\u00eda no ha habilitado tu acceso a documentos.',
                ),
                trailing: funciones.documents
                    ? const Icon(Icons.chevron_right)
                    : const Icon(Icons.lock_outline),
                onTap: funciones.documents
                    ? () => context.push('/documents')
                    : null,
              ),
            ),
            Card(
              child: ListTile(
                key: const Key('documentation-certificates'),
                leading: const Icon(Icons.verified_user_outlined),
                title: const Text('Solicitar certificados'),
                subtitle: Text(
                  funciones.certificates
                      ? 'Consulta los certificados disponibles y el estado de tus solicitudes. Necesitas tu certificado digital preparado por el despacho.'
                      : 'El despacho todav\u00eda no ha habilitado la solicitud de certificados para tu empresa.',
                ),
                trailing: funciones.certificates
                    ? const Icon(Icons.chevron_right)
                    : const Icon(Icons.lock_outline),
                onTap: funciones.certificates
                    ? () => context.push('/certificates')
                    : null,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
