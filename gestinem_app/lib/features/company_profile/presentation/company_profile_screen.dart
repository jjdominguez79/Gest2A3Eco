import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/company_profile.dart';
import 'company_profile_providers.dart';

/// Pantalla de solo lectura con la ficha empresarial del cliente.
class CompanyProfileScreen extends ConsumerWidget {
  const CompanyProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profileAsync = ref.watch(companyProfileProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Mi empresa')),
      body: SafeArea(
        top: false,
        minimum: const EdgeInsets.only(bottom: 12),
        child: profileAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) =>
              Center(child: Text('Error al cargar el perfil: $error')),
          data: (profile) => _ProfileContent(profile: profile),
        ),
      ),
    );
  }
}

class _ProfileContent extends StatelessWidget {
  const _ProfileContent({required this.profile});

  final CompanyProfile profile;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  profile.legalName ?? profile.name,
                  style: theme.textTheme.titleLarge,
                ),
                if (profile.taxId != null) ...[
                  const SizedBox(height: 8),
                  _InfoRow(label: 'NIF/CIF', value: profile.taxId!),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Direccion', style: theme.textTheme.titleMedium),
                const SizedBox(height: 8),
                if (profile.address != null)
                  _InfoRow(label: 'Direccion', value: profile.address!),
                if (profile.postalCode != null)
                  _InfoRow(label: 'Codigo postal', value: profile.postalCode!),
                if (profile.city != null)
                  _InfoRow(label: 'Poblacion', value: profile.city!),
                if (profile.province != null)
                  _InfoRow(label: 'Provincia', value: profile.province!),
                if (profile.country != null)
                  _InfoRow(label: 'Pais', value: profile.country!),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Contacto', style: theme.textTheme.titleMedium),
                const SizedBox(height: 8),
                if (profile.phone != null)
                  _InfoRow(label: 'Telefono', value: profile.phone!),
                if (profile.email != null)
                  _InfoRow(label: 'Correo', value: profile.email!),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
