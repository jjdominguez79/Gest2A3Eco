import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/company_a3_controller.dart';

class CompanyA3SettingsPage extends ConsumerStatefulWidget {
  const CompanyA3SettingsPage({
    super.key,
    required this.token,
    required this.companyId,
    required this.companyName,
  });

  final String token;
  final String companyId;
  final String companyName;

  @override
  ConsumerState<CompanyA3SettingsPage> createState() =>
      _CompanyA3SettingsPageState();
}

class _CompanyA3SettingsPageState extends ConsumerState<CompanyA3SettingsPage> {
  final _formKey = GlobalKey<FormState>();
  final _codeController = TextEditingController();
  final _pathController = TextEditingController();
  bool _enabled = false;
  String? _importMode;
  bool _initialized = false;

  @override
  void dispose() {
    _codeController.dispose();
    _pathController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scope = CompanyA3Scope(
      token: widget.token,
      companyId: widget.companyId,
    );
    final state = ref.watch(companyA3SettingsControllerProvider(scope));
    final controller = ref.read(
      companyA3SettingsControllerProvider(scope).notifier,
    );
    final settings = state.settings;

    if (!_initialized && settings != null) {
      _initialized = true;
      _enabled = settings.a3Enabled;
      _importMode = settings.a3ImportMode ?? 'manual';
      _codeController.text = settings.a3CompanyCode ?? '';
      _pathController.text = settings.a3ExportPath ?? '';
    }

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFFF5F7FA),
        borderRadius: BorderRadius.circular(18),
      ),
      padding: const EdgeInsets.all(24),
      child: state.isLoading
          ? const Center(child: CircularProgressIndicator())
          : settings == null
          ? Center(
              child: Text(
                state.errorMessage ?? 'No se pudo cargar la configuración A3.',
              ),
            )
          : Align(
              alignment: Alignment.topLeft,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'Configuración A3',
                                style: TextStyle(
                                  fontSize: 28,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              const SizedBox(height: 8),
                              Text(
                                'Empresa activa: ${widget.companyName}. Esta configuración afecta al snapshot de los lotes futuros.',
                              ),
                            ],
                          ),
                        ),
                        FilledButton.icon(
                          onPressed: !settings.canEdit || state.isSaving
                              ? null
                              : () => _save(controller),
                          icon: state.isSaving
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: Colors.white,
                                  ),
                                )
                              : const Icon(Icons.save_rounded),
                          label: const Text('Guardar'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 24),
                    if (state.errorMessage != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: Text(
                          state.errorMessage!,
                          style: const TextStyle(color: Colors.redAccent),
                        ),
                      ),
                    if (!settings.canEdit)
                      const Padding(
                        padding: EdgeInsets.only(bottom: 16),
                        child: Text(
                          'Solo los administradores de la empresa pueden editar esta configuración.',
                        ),
                      ),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: Form(
                          key: _formKey,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              SwitchListTile.adaptive(
                                contentPadding: EdgeInsets.zero,
                                value: _enabled,
                                onChanged: settings.canEdit
                                    ? (value) =>
                                          setState(() => _enabled = value)
                                    : null,
                                title: const Text('Habilitar integración A3'),
                                subtitle: const Text(
                                  'No bloquea la generación manual de lotes ni la exportación `.dat`.',
                                ),
                              ),
                              const SizedBox(height: 16),
                              TextFormField(
                                controller: _codeController,
                                enabled: settings.canEdit,
                                decoration: const InputDecoration(
                                  labelText: 'Código empresa A3',
                                  hintText: '00001',
                                  border: OutlineInputBorder(),
                                ),
                                validator: (value) {
                                  final normalized = value?.trim() ?? '';
                                  if (normalized.isEmpty) {
                                    return null;
                                  }
                                  if (!RegExp(
                                    r'^\d{1,5}$',
                                  ).hasMatch(normalized)) {
                                    return 'Usa entre 1 y 5 dígitos.';
                                  }
                                  return null;
                                },
                              ),
                              const SizedBox(height: 16),
                              DropdownButtonFormField<String>(
                                initialValue: _importMode,
                                decoration: const InputDecoration(
                                  labelText: 'Modo de importación',
                                  border: OutlineInputBorder(),
                                ),
                                items: const [
                                  DropdownMenuItem(
                                    value: 'manual',
                                    child: Text('Manual'),
                                  ),
                                  DropdownMenuItem(
                                    value: 'shared_folder',
                                    child: Text('Carpeta compartida'),
                                  ),
                                  DropdownMenuItem(
                                    value: 'future_connector',
                                    child: Text('Conector futuro'),
                                  ),
                                ],
                                onChanged: settings.canEdit
                                    ? (value) =>
                                          setState(() => _importMode = value)
                                    : null,
                              ),
                              const SizedBox(height: 16),
                              TextFormField(
                                controller: _pathController,
                                enabled: settings.canEdit,
                                decoration: const InputDecoration(
                                  labelText: 'Ruta de exportación',
                                  hintText: r'\\servidor\a3\import',
                                  border: OutlineInputBorder(),
                                ),
                              ),
                              const SizedBox(height: 12),
                              Text(
                                'Última actualización: ${_formatDateTime(settings.updatedAt)}',
                                style: const TextStyle(
                                  color: Color(0xFF62717E),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
    );
  }

  Future<void> _save(CompanyA3SettingsController controller) async {
    if (!_formKey.currentState!.validate()) {
      return;
    }
    final ok = await controller.save(
      a3Enabled: _enabled,
      a3CompanyCode: _codeController.text.trim(),
      a3ExportPath: _pathController.text.trim(),
      a3ImportMode: _importMode,
    );
    if (!mounted || !ok) {
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('Configuración A3 guardada.')));
  }

  String _formatDateTime(DateTime value) {
    final local = value.toLocal();
    return '${local.day.toString().padLeft(2, '0')}/${local.month.toString().padLeft(2, '0')}/${local.year} ${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
  }
}
