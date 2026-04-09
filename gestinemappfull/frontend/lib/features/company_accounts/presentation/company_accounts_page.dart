import 'package:flutter/material.dart';

import '../../../core/models/company_account_model.dart';
import '../../../core/models/global_third_party_model.dart';
import '../../../core/network/api_client.dart';

class CompanyAccountsPage extends StatefulWidget {
  const CompanyAccountsPage({
    super.key,
    required this.apiClient,
    required this.token,
    required this.companyId,
    required this.companyName,
  });

  final ApiClient apiClient;
  final String token;
  final String companyId;
  final String companyName;

  @override
  State<CompanyAccountsPage> createState() => _CompanyAccountsPageState();
}

class _CompanyAccountsPageState extends State<CompanyAccountsPage> {
  final _accountCodeController = TextEditingController();
  final _nameController = TextEditingController();

  bool _loading = true;
  String? _error;
  String? _accountTypeFilter;
  List<CompanyAccountModel> _items = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _accountCodeController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items = await widget.apiClient.getCompanyAccounts(
        token: widget.token,
        companyId: widget.companyId,
        accountCode: _accountCodeController.text.trim(),
        name: _nameController.text.trim(),
        accountType: _accountTypeFilter,
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
    final accountCode = TextEditingController();
    final name = TextEditingController();
    final taxId = TextEditingController();
    final legalName = TextEditingController();

    String accountType = 'other';
    GlobalThirdPartyModel? selectedThirdParty;
    List<GlobalThirdPartyModel> thirdParties = const [];

    try {
      thirdParties = await widget.apiClient.getThirdParties(
        token: widget.token,
      );
    } on ApiException {
      thirdParties = const [];
    }

    if (!mounted) {
      return;
    }

    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (dialogContext, setDialogState) {
            return AlertDialog(
              title: const Text('Nueva subcuenta'),
              content: SizedBox(
                width: 560,
                child: Form(
                  key: formKey,
                  child: SingleChildScrollView(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        TextFormField(
                          controller: accountCode,
                          decoration: const InputDecoration(
                            labelText: 'Codigo de cuenta',
                          ),
                          validator: (value) =>
                              (value == null || value.trim().isEmpty)
                              ? 'Introduce un codigo de cuenta.'
                              : null,
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: name,
                          decoration: const InputDecoration(
                            labelText: 'Nombre',
                          ),
                          validator: (value) =>
                              (value == null || value.trim().isEmpty)
                              ? 'Introduce un nombre.'
                              : null,
                        ),
                        const SizedBox(height: 12),
                        DropdownButtonFormField<String>(
                          initialValue: accountType,
                          decoration: const InputDecoration(
                            labelText: 'Tipo de cuenta',
                          ),
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
                              value: 'bank',
                              child: Text('Banco'),
                            ),
                            DropdownMenuItem(
                              value: 'expense',
                              child: Text('Gasto'),
                            ),
                            DropdownMenuItem(
                              value: 'income',
                              child: Text('Ingreso'),
                            ),
                            DropdownMenuItem(
                              value: 'tax',
                              child: Text('Impuesto'),
                            ),
                            DropdownMenuItem(
                              value: 'other',
                              child: Text('Otra'),
                            ),
                          ],
                          onChanged: (value) {
                            if (value != null) {
                              setDialogState(() => accountType = value);
                            }
                          },
                        ),
                        const SizedBox(height: 12),
                        DropdownButtonFormField<String?>(
                          initialValue: selectedThirdParty?.id,
                          decoration: const InputDecoration(
                            labelText: 'Tercero global vinculado',
                          ),
                          items: [
                            const DropdownMenuItem<String?>(
                              value: null,
                              child: Text('Sin vincular'),
                            ),
                            ...thirdParties.map(
                              (item) => DropdownMenuItem<String?>(
                                value: item.id,
                                child: Text(item.legalName),
                              ),
                            ),
                          ],
                          onChanged: (value) {
                            setDialogState(() {
                              selectedThirdParty = value == null
                                  ? null
                                  : thirdParties
                                        .cast<GlobalThirdPartyModel?>()
                                        .firstWhere(
                                          (item) => item?.id == value,
                                          orElse: () => null,
                                        );
                            });
                          },
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
                          controller: legalName,
                          decoration: const InputDecoration(
                            labelText: 'Razon social',
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
                      await widget.apiClient.createCompanyAccount(
                        token: widget.token,
                        companyId: widget.companyId,
                        accountCode: accountCode.text.trim(),
                        name: name.text.trim(),
                        accountType: accountType,
                        globalThirdPartyId: selectedThirdParty?.id,
                        taxId: taxId.text.trim().isEmpty
                            ? null
                            : taxId.text.trim(),
                        legalName: legalName.text.trim().isEmpty
                            ? null
                            : legalName.text.trim(),
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
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Plan contable',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 8),
                  Text('Subcuentas activas de ${widget.companyName}.'),
                ],
              ),
            ),
            FilledButton.icon(
              onPressed: _openCreateDialog,
              icon: const Icon(Icons.note_add_rounded),
              label: const Text('Nueva subcuenta'),
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
                controller: _accountCodeController,
                decoration: const InputDecoration(
                  labelText: 'Buscar por codigo',
                ),
              ),
            ),
            SizedBox(
              width: 280,
              child: TextField(
                controller: _nameController,
                decoration: const InputDecoration(
                  labelText: 'Buscar por nombre',
                ),
              ),
            ),
            SizedBox(
              width: 220,
              child: DropdownButtonFormField<String?>(
                initialValue: _accountTypeFilter,
                decoration: const InputDecoration(labelText: 'Tipo de cuenta'),
                items: const [
                  DropdownMenuItem<String?>(value: null, child: Text('Todos')),
                  DropdownMenuItem(value: 'client', child: Text('Cliente')),
                  DropdownMenuItem(value: 'supplier', child: Text('Proveedor')),
                  DropdownMenuItem(value: 'bank', child: Text('Banco')),
                  DropdownMenuItem(value: 'expense', child: Text('Gasto')),
                  DropdownMenuItem(value: 'income', child: Text('Ingreso')),
                  DropdownMenuItem(value: 'tax', child: Text('Impuesto')),
                  DropdownMenuItem(value: 'other', child: Text('Otra')),
                ],
                onChanged: (value) =>
                    setState(() => _accountTypeFilter = value),
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
                ? const Center(
                    child: Text('No hay subcuentas para la empresa activa.'),
                  )
                : ListView.separated(
                    itemCount: _items.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final item = _items[index];
                      return ListTile(
                        title: Text('${item.accountCode} · ${item.name}'),
                        subtitle: Text(
                          [
                            item.accountType,
                            if (item.taxId != null) item.taxId!,
                            if (item.legalName != null) item.legalName!,
                          ].join(' · '),
                        ),
                        trailing: Text(item.syncStatus),
                      );
                    },
                  ),
          ),
        ),
      ],
    );
  }
}
