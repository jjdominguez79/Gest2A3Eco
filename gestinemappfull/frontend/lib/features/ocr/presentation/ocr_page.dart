import 'package:flutter/material.dart';

import '../../../core/models/company_account_model.dart';
import '../../../core/models/global_third_party_model.dart';
import '../../../core/models/invoice_review_model.dart';
import '../../../core/models/invoice_review_pending_item_model.dart';
import '../../../core/models/invoice_review_suggestions_model.dart';
import '../../../core/network/api_client.dart';

class OcrPage extends StatefulWidget {
  const OcrPage({
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
  State<OcrPage> createState() => _OcrPageState();
}

class _OcrPageState extends State<OcrPage> {
  final _supplierNameController = TextEditingController();
  final _supplierTaxIdController = TextEditingController();
  final _invoiceNumberController = TextEditingController();
  final _invoiceDateController = TextEditingController();
  final _taxableBaseController = TextEditingController();
  final _taxRateController = TextEditingController();
  final _taxAmountController = TextEditingController();
  final _totalAmountController = TextEditingController();
  final _conceptController = TextEditingController();

  bool _loading = true;
  bool _saving = false;
  bool _confirming = false;
  bool _loadingSuggestions = false;
  String? _error;

  List<InvoiceReviewPendingItemModel> _pendingItems = const [];
  List<GlobalThirdPartyModel> _supplierOptions = const [];
  List<CompanyAccountModel> _supplierAccountOptions = const [];
  InvoiceReviewSuggestionsModel? _suggestions;
  String? _selectedDocumentId;
  InvoiceReviewModel? _currentReview;
  String? _selectedThirdPartyId;
  String? _selectedAccountId;

  @override
  void initState() {
    super.initState();
    _loadInitial();
  }

  @override
  void dispose() {
    _supplierNameController.dispose();
    _supplierTaxIdController.dispose();
    _invoiceNumberController.dispose();
    _invoiceDateController.dispose();
    _taxableBaseController.dispose();
    _taxRateController.dispose();
    _taxAmountController.dispose();
    _totalAmountController.dispose();
    _conceptController.dispose();
    super.dispose();
  }

  Future<void> _loadInitial() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final pending = await widget.apiClient.getPendingInvoiceReviews(
        token: widget.token,
        companyId: widget.companyId,
      );
      final thirdParties = await widget.apiClient.getThirdParties(
        token: widget.token,
      );
      final accounts = await widget.apiClient.getCompanyAccounts(
        token: widget.token,
        companyId: widget.companyId,
        accountType: 'supplier',
      );
      if (!mounted) return;
      setState(() {
        _pendingItems = pending;
        _supplierOptions = thirdParties
            .where(
              (item) =>
                  item.thirdPartyType == 'supplier' ||
                  item.thirdPartyType == 'both',
            )
            .toList();
        _supplierAccountOptions = accounts;
        _loading = false;
      });
      if (_pendingItems.isNotEmpty) {
        await _openPending(_pendingItems.first.documentId);
      }
    } on ApiException catch (exc) {
      if (!mounted) return;
      setState(() {
        _error = exc.message;
        _loading = false;
      });
    }
  }

  Future<void> _openPending(String documentId) async {
    setState(() {
      _selectedDocumentId = documentId;
      _error = null;
    });
    try {
      InvoiceReviewModel review;
      try {
        review = await widget.apiClient.getInvoiceReview(
          token: widget.token,
          companyId: widget.companyId,
          documentId: documentId,
        );
      } on ApiException {
        review = await widget.apiClient.initializeInvoiceReview(
          token: widget.token,
          companyId: widget.companyId,
          documentId: documentId,
        );
      }
      if (!mounted) return;
      _applyReview(review);
      await _refreshPending();
      await _loadSuggestions(documentId);
    } on ApiException catch (exc) {
      if (!mounted) return;
      setState(() => _error = exc.message);
    }
  }

  Future<void> _loadSuggestions(String documentId) async {
    setState(() => _loadingSuggestions = true);
    try {
      final suggestions = await widget.apiClient.getInvoiceReviewSuggestions(
        token: widget.token,
        companyId: widget.companyId,
        documentId: documentId,
      );
      if (!mounted) return;
      setState(() => _suggestions = suggestions);
    } on ApiException {
      if (!mounted) return;
      setState(() => _suggestions = null);
    } finally {
      if (mounted) {
        setState(() => _loadingSuggestions = false);
      }
    }
  }

  Future<void> _refreshPending() async {
    final pending = await widget.apiClient.getPendingInvoiceReviews(
      token: widget.token,
      companyId: widget.companyId,
    );
    if (!mounted) return;
    setState(() => _pendingItems = pending);
  }

  void _applyReview(InvoiceReviewModel review) {
    setState(() {
      _currentReview = review;
      _selectedThirdPartyId = review.supplierThirdPartyId;
      _selectedAccountId = review.supplierCompanyAccountId;
      _supplierNameController.text = review.supplierNameDetected ?? '';
      _supplierTaxIdController.text = review.supplierTaxIdDetected ?? '';
      _invoiceNumberController.text = review.invoiceNumber ?? '';
      _invoiceDateController.text = review.invoiceDate == null
          ? ''
          : review.invoiceDate!.toIso8601String().split('T').first;
      _taxableBaseController.text = _formatNumber(review.taxableBase);
      _taxRateController.text = _formatNumber(review.taxRate);
      _taxAmountController.text = _formatNumber(review.taxAmount);
      _totalAmountController.text = _formatNumber(review.totalAmount);
      _conceptController.text = review.concept ?? '';
    });
  }

  Future<void> _createThirdPartyQuick() async {
    final review = _currentReview;
    if (review == null) return;
    final nameController = TextEditingController(
      text: _supplierNameController.text.trim(),
    );
    final taxIdController = TextEditingController(
      text: _supplierTaxIdController.text.trim(),
    );
    try {
      await showDialog<void>(
        context: context,
        builder: (dialogContext) {
          return AlertDialog(
            title: const Text('Crear tercero global'),
            content: SizedBox(
              width: 420,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: nameController,
                    decoration: const InputDecoration(
                      labelText: 'Nombre legal',
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: taxIdController,
                    decoration: const InputDecoration(labelText: 'NIF/CIF'),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text('Cancelar'),
              ),
              FilledButton(
                onPressed: () async {
                  try {
                    final result = await widget.apiClient.quickCreateThirdParty(
                      token: widget.token,
                      thirdPartyType: 'supplier',
                      legalName: nameController.text.trim(),
                      taxId: taxIdController.text.trim(),
                      documentId: review.documentId,
                    );
                    if (!dialogContext.mounted) return;
                    Navigator.of(dialogContext).pop();
                    setState(() => _selectedThirdPartyId = result.item.id);
                    _supplierNameController.text = result.item.legalName;
                    _supplierTaxIdController.text = result.item.taxId ?? '';
                    await _reloadMasterData();
                    await _saveReview();
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
    } finally {
      nameController.dispose();
      taxIdController.dispose();
    }
  }

  Future<void> _createAccountQuick() async {
    final review = _currentReview;
    if (review == null) return;
    final code = await widget.apiClient.getNextCompanyAccountCode(
      token: widget.token,
      companyId: widget.companyId,
      accountType: 'supplier',
    );
    if (!mounted) return;
    final nameController = TextEditingController(
      text: _supplierNameController.text.trim().isEmpty
          ? review.supplierNameDetected ?? ''
          : _supplierNameController.text.trim(),
    );
    final codeController = TextEditingController(text: code);
    try {
      await showDialog<void>(
        context: context,
        builder: (dialogContext) {
          return AlertDialog(
            title: const Text('Crear subcuenta'),
            content: SizedBox(
              width: 440,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: codeController,
                    decoration: const InputDecoration(labelText: 'Codigo'),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: nameController,
                    decoration: const InputDecoration(labelText: 'Nombre'),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text('Cancelar'),
              ),
              FilledButton(
                onPressed: () async {
                  try {
                    final result = await widget.apiClient
                        .quickCreateCompanyAccount(
                          token: widget.token,
                          companyId: widget.companyId,
                          accountType: 'supplier',
                          name: nameController.text.trim(),
                          globalThirdPartyId: _selectedThirdPartyId,
                          taxId: _supplierTaxIdController.text.trim(),
                          legalName: _supplierNameController.text.trim(),
                          accountCode: codeController.text.trim(),
                          documentId: review.documentId,
                        );
                    if (!dialogContext.mounted) return;
                    Navigator.of(dialogContext).pop();
                    setState(() => _selectedAccountId = result.item.id);
                    await _reloadMasterData();
                    await _saveReview();
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
    } finally {
      nameController.dispose();
      codeController.dispose();
    }
  }

  Future<void> _reloadMasterData() async {
    final thirdParties = await widget.apiClient.getThirdParties(
      token: widget.token,
    );
    final accounts = await widget.apiClient.getCompanyAccounts(
      token: widget.token,
      companyId: widget.companyId,
      accountType: 'supplier',
    );
    if (!mounted) return;
    setState(() {
      _supplierOptions = thirdParties
          .where(
            (item) =>
                item.thirdPartyType == 'supplier' ||
                item.thirdPartyType == 'both',
          )
          .toList();
      _supplierAccountOptions = accounts;
    });
  }

  void _applyThirdPartySuggestion(SuggestedThirdPartyModel suggestion) {
    setState(() => _selectedThirdPartyId = suggestion.id);
    _supplierNameController.text = suggestion.legalName;
    _supplierTaxIdController.text =
        suggestion.taxId ?? _supplierTaxIdController.text;
  }

  void _applyAccountSuggestion(SuggestedCompanyAccountModel suggestion) {
    setState(() => _selectedAccountId = suggestion.id);
  }

  Future<void> _saveReview() async {
    await _persistReview(showMessage: true);
  }

  Future<InvoiceReviewModel> _persistReview({required bool showMessage}) async {
    final review = _currentReview;
    if (review == null) {
      throw ApiException('No hay factura seleccionada.');
    }
    setState(() => _saving = true);
    try {
      final updated = await widget.apiClient.updateInvoiceReview(
        token: widget.token,
        companyId: widget.companyId,
        documentId: review.documentId,
        supplierThirdPartyId: _selectedThirdPartyId,
        supplierCompanyAccountId: _selectedAccountId,
        supplierNameDetected: _supplierNameController.text.trim(),
        supplierTaxIdDetected: _supplierTaxIdController.text.trim(),
        invoiceNumber: _invoiceNumberController.text.trim(),
        invoiceDate: _invoiceDateController.text.trim().isEmpty
            ? null
            : _invoiceDateController.text.trim(),
        taxableBase: _taxableBaseController.text,
        taxRate: _taxRateController.text,
        taxAmount: _taxAmountController.text,
        totalAmount: _totalAmountController.text,
        concept: _conceptController.text.trim(),
      );
      if (!mounted) return updated;
      _applyReview(updated);
      await _refreshPending();
      if (!mounted) return updated;
      if (showMessage) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Revision guardada.')));
      }
      return updated;
    } on ApiException catch (exc) {
      if (!mounted) return review;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(exc.message)));
      rethrow;
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  Future<void> _confirmReview() async {
    final review = _currentReview;
    if (review == null) return;
    setState(() => _confirming = true);
    try {
      await _persistReview(showMessage: false);
      final confirmed = await widget.apiClient.confirmInvoiceReview(
        token: widget.token,
        companyId: widget.companyId,
        documentId: review.documentId,
      );
      if (!mounted) return;
      await _refreshPending();
      if (!mounted) return;
      String? nextId;
      for (final item in _pendingItems) {
        if (item.documentId != confirmed.documentId) {
          nextId = item.documentId;
          break;
        }
      }
      if (nextId != null) {
        await _openPending(nextId);
      } else {
        setState(() {
          _currentReview = null;
          _selectedDocumentId = null;
        });
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Factura confirmada y enviada a pending_accounting.'),
        ),
      );
    } on ApiException catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(exc.message)));
    } finally {
      if (mounted) {
        setState(() => _confirming = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFFF5F7FA),
        borderRadius: BorderRadius.circular(18),
      ),
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : Row(
              children: [
                _buildQueuePanel(),
                const VerticalDivider(width: 1),
                Expanded(
                  child: _currentReview == null
                      ? _buildEmptyState()
                      : Row(
                          children: [
                            Expanded(child: _buildOcrPanel()),
                            const VerticalDivider(width: 1),
                            Expanded(child: _buildFormPanel()),
                          ],
                        ),
                ),
              ],
            ),
    );
  }

  Widget _buildQueuePanel() {
    return Container(
      width: 320,
      padding: const EdgeInsets.all(20),
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.horizontal(left: Radius.circular(18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'OCR Facturas',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          Text('Facturas recibidas pendientes en ${widget.companyName}.'),
          const SizedBox(height: 16),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(
                _error!,
                style: const TextStyle(color: Colors.redAccent),
              ),
            ),
          FilledButton.icon(
            onPressed: _loadInitial,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Recargar cola'),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: _pendingItems.isEmpty
                ? const Center(
                    child: Text(
                      'No hay facturas recibidas pendientes de revision.',
                    ),
                  )
                : ListView.separated(
                    itemCount: _pendingItems.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final item = _pendingItems[index];
                      final selected = item.documentId == _selectedDocumentId;
                      return ListTile(
                        selected: selected,
                        selectedTileColor: const Color(0xFFEAF4FB),
                        onTap: () => _openPending(item.documentId),
                        title: Text(
                          item.documentOriginalFilename,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        subtitle: Text(
                          '${_formatReviewStatus(item.reviewStatus)} · ${item.invoiceNumber ?? 'Sin numero'}',
                        ),
                        trailing: item.totalAmount == null
                            ? null
                            : Text(item.totalAmount!.toStringAsFixed(2)),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildOcrPanel() {
    final review = _currentReview!;
    return Container(
      padding: const EdgeInsets.all(20),
      color: Colors.white,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            review.documentOriginalFilename ?? 'Documento',
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _StatusBadge(
                label: 'Revision',
                value: _formatReviewStatus(review.reviewStatus),
              ),
              _StatusBadge(
                label: 'OCR',
                value: _formatOcrStatus(review.ocrStatus),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Text(
            'Texto OCR bruto',
            style: TextStyle(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFFF7F9FC),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: const Color(0xFFD8E0E8)),
              ),
              child: SingleChildScrollView(
                child: SelectableText(
                  review.ocrText?.trim().isNotEmpty == true
                      ? review.ocrText!
                      : 'No hay texto OCR disponible.',
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFormPanel() {
    return Container(
      padding: const EdgeInsets.all(20),
      color: const Color(0xFFFCFDFE),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Datos revisables',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: SingleChildScrollView(
              child: Wrap(
                spacing: 16,
                runSpacing: 16,
                children: [
                  _buildTextField(
                    _supplierNameController,
                    'Proveedor detectado',
                    width: 280,
                  ),
                  _buildTextField(
                    _supplierTaxIdController,
                    'NIF/CIF detectado',
                    width: 220,
                  ),
                  _buildTextField(
                    _invoiceNumberController,
                    'Numero factura',
                    width: 220,
                  ),
                  _buildTextField(
                    _invoiceDateController,
                    'Fecha',
                    width: 160,
                    hintText: 'YYYY-MM-DD',
                  ),
                  _buildTextField(
                    _taxableBaseController,
                    'Base imponible',
                    width: 160,
                  ),
                  _buildTextField(_taxRateController, 'IVA %', width: 120),
                  _buildTextField(
                    _taxAmountController,
                    'Cuota IVA',
                    width: 160,
                  ),
                  _buildTextField(_totalAmountController, 'Total', width: 160),
                  _buildTextField(
                    _conceptController,
                    'Concepto',
                    width: 580,
                    maxLines: 3,
                  ),
                  _buildSuggestionPanel(),
                  SizedBox(
                    width: 320,
                    child: DropdownButtonFormField<String?>(
                      key: ValueKey(
                        'third-party-${_currentReview?.documentId}-${_selectedThirdPartyId ?? 'none'}',
                      ),
                      initialValue: _selectedThirdPartyId,
                      decoration: const InputDecoration(
                        labelText: 'Tercero global',
                      ),
                      items: [
                        const DropdownMenuItem<String?>(
                          value: null,
                          child: Text('Sin vincular'),
                        ),
                        ..._supplierOptions.map(
                          (item) => DropdownMenuItem<String?>(
                            value: item.id,
                            child: Text(
                              '${item.legalName} ${item.taxId ?? ''}'.trim(),
                            ),
                          ),
                        ),
                      ],
                      onChanged: (value) =>
                          setState(() => _selectedThirdPartyId = value),
                    ),
                  ),
                  SizedBox(
                    width: 320,
                    child: DropdownButtonFormField<String?>(
                      key: ValueKey(
                        'account-${_currentReview?.documentId}-${_selectedAccountId ?? 'none'}',
                      ),
                      initialValue: _selectedAccountId,
                      decoration: const InputDecoration(
                        labelText: 'Subcuenta proveedor',
                      ),
                      items: [
                        const DropdownMenuItem<String?>(
                          value: null,
                          child: Text('Sin vincular'),
                        ),
                        ..._supplierAccountOptions.map(
                          (item) => DropdownMenuItem<String?>(
                            value: item.id,
                            child: Text('${item.accountCode} ${item.name}'),
                          ),
                        ),
                      ],
                      onChanged: (value) =>
                          setState(() => _selectedAccountId = value),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              OutlinedButton.icon(
                onPressed: _saving || _confirming
                    ? null
                    : _createThirdPartyQuick,
                icon: const Icon(Icons.person_add_alt_1_rounded),
                label: const Text('Crear tercero'),
              ),
              const SizedBox(width: 12),
              OutlinedButton.icon(
                onPressed: _saving || _confirming ? null : _createAccountQuick,
                icon: const Icon(Icons.playlist_add_rounded),
                label: const Text('Crear subcuenta'),
              ),
              const SizedBox(width: 12),
              OutlinedButton.icon(
                onPressed: _saving || _confirming ? null : _saveReview,
                icon: _saving
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.save_rounded),
                label: const Text('Guardar'),
              ),
              const SizedBox(width: 12),
              FilledButton.icon(
                onPressed: _saving || _confirming ? null : _confirmReview,
                icon: _confirming
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.check_circle_rounded),
                label: const Text('Confirmar'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return const Center(
      child: Text(
        'Selecciona una factura recibida pendiente para revisar sus datos OCR.',
      ),
    );
  }

  Widget _buildTextField(
    TextEditingController controller,
    String label, {
    required double width,
    int maxLines = 1,
    String? hintText,
  }) {
    return SizedBox(
      width: width,
      child: TextField(
        controller: controller,
        maxLines: maxLines,
        decoration: InputDecoration(labelText: label, hintText: hintText),
      ),
    );
  }

  Widget _buildSuggestionPanel() {
    return Container(
      width: 660,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFF7FAFD),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFD8E0E8)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                'Sugerencias automaticas',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
              const Spacer(),
              TextButton(
                onPressed: _currentReview == null || _loadingSuggestions
                    ? null
                    : () => _loadSuggestions(_currentReview!.documentId),
                child: const Text('Refrescar'),
              ),
            ],
          ),
          if (_loadingSuggestions)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: LinearProgressIndicator(),
            )
          else if (_suggestions == null)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text('No hay sugerencias cargadas.'),
            )
          else ...[
            const SizedBox(height: 8),
            const Text('Terceros globales'),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _suggestions!.suggestedThirdParties.isEmpty
                  ? const [Text('Sin coincidencias.')]
                  : _suggestions!.suggestedThirdParties.map((item) {
                      return ActionChip(
                        label: Text(
                          '${item.legalName} · ${item.taxId ?? '-'} · ${(item.score * 100).toStringAsFixed(0)}%',
                        ),
                        onPressed: () => _applyThirdPartySuggestion(item),
                      );
                    }).toList(),
            ),
            const SizedBox(height: 12),
            const Text('Subcuentas'),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _suggestions!.suggestedCompanyAccounts.isEmpty
                  ? const [Text('Sin coincidencias.')]
                  : _suggestions!.suggestedCompanyAccounts.map((item) {
                      return ActionChip(
                        label: Text(
                          '${item.accountCode} ${item.name} · ${(item.score * 100).toStringAsFixed(0)}%',
                        ),
                        onPressed: () => _applyAccountSuggestion(item),
                      );
                    }).toList(),
            ),
          ],
        ],
      ),
    );
  }

  String _formatReviewStatus(String status) {
    switch (status) {
      case 'pending':
        return 'Pendiente';
      case 'reviewed':
        return 'Revisada';
      case 'confirmed':
        return 'Confirmada';
      case 'error':
        return 'Error';
      default:
        return status;
    }
  }

  String _formatOcrStatus(String? status) {
    switch (status) {
      case 'processed':
        return 'Procesado';
      case 'reviewed':
        return 'Revisado';
      case 'error':
        return 'Error';
      case 'pending':
        return 'Pendiente';
      default:
        return 'Sin OCR';
    }
  }

  String _formatNumber(double? value) {
    if (value == null) {
      return '';
    }
    if (value == value.roundToDouble()) {
      return value.toStringAsFixed(0);
    }
    return value.toStringAsFixed(2);
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFEAF4FB),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(fontSize: 12, color: Color(0xFF556677)),
          ),
          const SizedBox(height: 4),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}
