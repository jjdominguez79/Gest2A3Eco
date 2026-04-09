import 'package:flutter/material.dart';

import '../../../core/models/global_third_party_model.dart';
import '../../../core/network/api_client.dart';

class ThirdPartiesPage extends StatefulWidget {
  const ThirdPartiesPage({
    super.key,
    required this.apiClient,
    required this.token,
  });

  final ApiClient apiClient;
  final String token;

  @override
  State<ThirdPartiesPage> createState() => _ThirdPartiesPageState();
}

class _ThirdPartiesPageState extends State<ThirdPartiesPage> {
  final _taxIdController = TextEditingController();
  final _legalNameController = TextEditingController();

  bool _loading = true;
  String? _error;
  List<GlobalThirdPartyModel> _items = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _taxIdController.dispose();
    _legalNameController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items = await widget.apiClient.getThirdParties(
        token: widget.token,
        taxId: _taxIdController.text.trim(),
        legalName: _legalNameController.text.trim(),
      );
      setState(() {
        _items = items;
        _loading = false;
      });
    } on ApiException catch (exc) {
      setState(() {
        _error = exc.message;
        _loading = false;
      });
    }
  }

  Future<void> _openCreateDialog() async {
    final formKey = GlobalKey<FormState>();
    final legalName = TextEditingController();
    final taxId = TextEditingController();
    final tradeName = TextEditingController();
    final email = TextEditingController();
    final phone = TextEditingController();
    String thirdPartyType = 'client';

    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (dialogContext, setDialogState) {
            return AlertDialog(
              title: const Text('Nuevo tercero global'),
              content: SizedBox(
                width: 520,
                child: Form(
                  key: formKey,
                  child: SingleChildScrollView(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        DropdownButtonFormField<String>(
                          initialValue: thirdPartyType,
                          decoration: const InputDecoration(labelText: 'Tipo'),
                          items: const [
                            DropdownMenuItem(
                              value: 'client',
                              child: Text('Cliente'),
                            ),
                            DropdownMenuItem(
                              value: 'supplier',
                              child: Text('Proveedor'),
                            ),
                            DropdownMenuItem(
                              value: 'both',
                              child: Text('Ambos'),
                            ),
                            DropdownMenuItem(
                              value: 'bank',
                              child: Text('Banco'),
                            ),
                            DropdownMenuItem(
                              value: 'other',
                              child: Text('Otro'),
                            ),
                          ],
                          onChanged: (value) {
                            if (value != null) {
                              setDialogState(() => thirdPartyType = value);
                            }
                          },
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: legalName,
                          decoration: const InputDecoration(
                            labelText: 'Razon social',
                          ),
                          validator: (value) =>
                              (value == null || value.trim().isEmpty)
                              ? 'Introduce una razon social.'
                              : null,
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: taxId,
                          decoration: const InputDecoration(
                            labelText: 'NIF/CIF',
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: tradeName,
                          decoration: const InputDecoration(
                            labelText: 'Nombre comercial',
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: email,
                          decoration: const InputDecoration(labelText: 'Email'),
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: phone,
                          decoration: const InputDecoration(
                            labelText: 'Telefono',
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(dialogContext).pop(),
                  child: const Text('Cancelar'),
                ),
                FilledButton(
                  onPressed: () async {
                    if (!formKey.currentState!.validate()) {
                      return;
                    }
                    try {
                      await widget.apiClient.createThirdParty(
                        token: widget.token,
                        thirdPartyType: thirdPartyType,
                        legalName: legalName.text.trim(),
                        taxId: taxId.text.trim().isEmpty
                            ? null
                            : taxId.text.trim(),
                        tradeName: tradeName.text.trim().isEmpty
                            ? null
                            : tradeName.text.trim(),
                        email: email.text.trim().isEmpty
                            ? null
                            : email.text.trim(),
                        phone: phone.text.trim().isEmpty
                            ? null
                            : phone.text.trim(),
                      );
                      if (!dialogContext.mounted) return;
                      Navigator.of(dialogContext).pop();
                      await _load();
                    } on ApiException catch (exc) {
                      if (!dialogContext.mounted) return;
                      ScaffoldMessenger.of(
                        dialogContext,
                      ).showSnackBar(SnackBar(content: Text(exc.message)));
                    }
                  },
                  child: const Text('Crear'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Terceros globales',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                  SizedBox(height: 8),
                  Text('Maestro comun reutilizable entre empresas.'),
                ],
              ),
            ),
            FilledButton.icon(
              onPressed: _openCreateDialog,
              icon: const Icon(Icons.person_add_alt_1_rounded),
              label: const Text('Nuevo tercero'),
            ),
          ],
        ),
        const SizedBox(height: 24),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            SizedBox(
              width: 220,
              child: TextField(
                controller: _taxIdController,
                decoration: const InputDecoration(
                  labelText: 'Buscar por NIF/CIF',
                ),
              ),
            ),
            SizedBox(
              width: 280,
              child: TextField(
                controller: _legalNameController,
                decoration: const InputDecoration(
                  labelText: 'Buscar por nombre',
                ),
              ),
            ),
            FilledButton(onPressed: _load, child: const Text('Buscar')),
          ],
        ),
        const SizedBox(height: 20),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text(
              _error!,
              style: const TextStyle(color: Colors.redAccent),
            ),
          ),
        Expanded(
          child: Container(
            width: double.infinity,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: const Color(0xFFD8E0E8)),
            ),
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _items.isEmpty
                ? const Center(child: Text('No hay terceros globales.'))
                : ListView.separated(
                    itemCount: _items.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final item = _items[index];
                      return ListTile(
                        title: Text(item.legalName),
                        subtitle: Text(
                          [
                            if (item.taxId != null) item.taxId!,
                            item.thirdPartyType,
                            if (item.tradeName != null) item.tradeName!,
                          ].join(' · '),
                        ),
                        trailing: Text(item.email ?? item.phone ?? ''),
                      );
                    },
                  ),
          ),
        ),
      ],
    );
  }
}
