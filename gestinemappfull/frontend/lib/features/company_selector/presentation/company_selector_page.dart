import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/company_model.dart';
import '../../../core/state/session_controller.dart';

class CompanySelectorPage extends ConsumerWidget {
  const CompanySelectorPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionControllerProvider);
    final controller = ref.read(sessionControllerProvider.notifier);

    return Scaffold(
      body: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Seleccion de empresa',
                        style: TextStyle(
                          fontSize: 30,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      SizedBox(height: 8),
                      Text(
                        'Selecciona la empresa activa para entrar al dashboard.',
                      ),
                    ],
                  ),
                ),
                OutlinedButton.icon(
                  onPressed: session.isBusy
                      ? null
                      : () => _openCreateCompanyDialog(context, controller),
                  icon: const Icon(Icons.add_business_rounded),
                  label: const Text('Nueva empresa'),
                ),
              ],
            ),
            const SizedBox(height: 24),
            if (session.errorMessage != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Text(
                  session.errorMessage!,
                  style: const TextStyle(color: Colors.redAccent),
                ),
              ),
            Expanded(
              child: session.companies.isEmpty
                  ? const Center(
                      child: Text(
                        'No hay empresas asignadas. Crea la primera para continuar.',
                      ),
                    )
                  : GridView.builder(
                      gridDelegate:
                          const SliverGridDelegateWithFixedCrossAxisCount(
                            crossAxisCount: 3,
                            crossAxisSpacing: 16,
                            mainAxisSpacing: 16,
                            childAspectRatio: 1.6,
                          ),
                      itemCount: session.companies.length,
                      itemBuilder: (context, index) {
                        final company = session.companies[index];
                        return _CompanyCard(
                          company: company,
                          isBusy: session.isBusy,
                          onTap: () => controller.selectCompany(company),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openCreateCompanyDialog(
    BuildContext context,
    SessionController controller,
  ) async {
    final nameController = TextEditingController();
    final cifController = TextEditingController();
    final formKey = GlobalKey<FormState>();

    await showDialog<void>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Nueva empresa'),
          content: SizedBox(
            width: 420,
            child: Form(
              key: formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextFormField(
                    controller: nameController,
                    decoration: const InputDecoration(labelText: 'Nombre'),
                    validator: (value) =>
                        (value == null || value.trim().isEmpty)
                        ? 'Introduce un nombre.'
                        : null,
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: cifController,
                    decoration: const InputDecoration(labelText: 'CIF'),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () async {
                if (formKey.currentState!.validate()) {
                  await controller.createCompany(
                    name: nameController.text.trim(),
                    cif: cifController.text.trim().isEmpty
                        ? null
                        : cifController.text.trim(),
                  );
                  if (context.mounted) {
                    Navigator.of(context).pop();
                  }
                }
              },
              child: const Text('Crear'),
            ),
          ],
        );
      },
    );
  }
}

class _CompanyCard extends StatelessWidget {
  const _CompanyCard({
    required this.company,
    required this.isBusy,
    required this.onTap,
  });

  final CompanyModel company;
  final bool isBusy;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: isBusy ? null : onTap,
      borderRadius: BorderRadius.circular(20),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: const Color(0xFFD8E0E8)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(
              Icons.apartment_rounded,
              size: 32,
              color: Color(0xFF005F73),
            ),
            const SizedBox(height: 20),
            Text(
              company.name,
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            Text(company.cif ?? 'Sin CIF'),
            const Spacer(),
            Text(
              'Rol: ${company.role}',
              style: const TextStyle(color: Color(0xFF5D7387)),
            ),
          ],
        ),
      ),
    );
  }
}
