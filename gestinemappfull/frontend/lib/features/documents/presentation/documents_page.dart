import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../../core/models/document_model.dart';
import '../../../core/network/api_client.dart';

class DocumentsPage extends StatefulWidget {
  const DocumentsPage({
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
  State<DocumentsPage> createState() => _DocumentsPageState();
}

class _DocumentsPageState extends State<DocumentsPage> {
  final _filenameController = TextEditingController();
  String? _documentTypeFilter;
  String? _workflowStatusFilter;

  bool _loading = true;
  String? _error;
  List<DocumentModel> _items = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _filenameController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items = await widget.apiClient.getDocuments(
        token: widget.token,
        companyId: widget.companyId,
        documentType: _documentTypeFilter,
        workflowStatus: _workflowStatusFilter,
        originalFilename: _filenameController.text.trim(),
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

  Future<void> _pickAndUpload() async {
    final result = await FilePicker.platform.pickFiles(withData: true);
    if (result == null || result.files.isEmpty) {
      return;
    }
    if (!mounted) {
      return;
    }
    final file = result.files.first;
    if (file.bytes == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No se pudieron leer los bytes del archivo.'),
        ),
      );
      return;
    }

    try {
      await widget.apiClient.uploadDocument(
        token: widget.token,
        companyId: widget.companyId,
        bytes: file.bytes!,
        filename: file.name,
      );
      if (!mounted) return;
      await _load();
    } on ApiException catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(exc.message)));
    }
  }

  Future<void> _openEditDialog(DocumentModel document) async {
    String selectedType = document.documentType;
    String selectedStatus = document.workflowStatus;

    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (dialogContext, setDialogState) {
            return AlertDialog(
              title: Text('Editar ${document.originalFilename}'),
              content: SizedBox(
                width: 440,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    DropdownButtonFormField<String>(
                      value: selectedType,
                      decoration: const InputDecoration(
                        labelText: 'Tipo documental',
                      ),
                      items: const [
                        DropdownMenuItem(
                          value: 'invoice_issued',
                          child: Text('Factura emitida'),
                        ),
                        DropdownMenuItem(
                          value: 'invoice_received',
                          child: Text('Factura recibida'),
                        ),
                        DropdownMenuItem(
                          value: 'bank_statement',
                          child: Text('Extracto bancario'),
                        ),
                        DropdownMenuItem(
                          value: 'contract',
                          child: Text('Contrato'),
                        ),
                        DropdownMenuItem(
                          value: 'bank_receipt',
                          child: Text('Recibo bancario'),
                        ),
                        DropdownMenuItem(
                          value: 'unassigned',
                          child: Text('Sin asignar'),
                        ),
                        DropdownMenuItem(value: 'other', child: Text('Otro')),
                      ],
                      onChanged: (value) {
                        if (value != null) {
                          setDialogState(() => selectedType = value);
                        }
                      },
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      value: selectedStatus,
                      decoration: const InputDecoration(
                        labelText: 'Estado de workflow',
                      ),
                      items: const [
                        DropdownMenuItem(value: 'inbox', child: Text('Inbox')),
                        DropdownMenuItem(
                          value: 'classified',
                          child: Text('Clasificado'),
                        ),
                        DropdownMenuItem(
                          value: 'pending_review',
                          child: Text('Pendiente revision'),
                        ),
                        DropdownMenuItem(
                          value: 'pending_ocr',
                          child: Text('Pendiente OCR'),
                        ),
                        DropdownMenuItem(
                          value: 'pending_accounting',
                          child: Text('Pendiente contabilizar'),
                        ),
                        DropdownMenuItem(
                          value: 'accounted',
                          child: Text('Contabilizado'),
                        ),
                        DropdownMenuItem(
                          value: 'archived',
                          child: Text('Archivado'),
                        ),
                        DropdownMenuItem(value: 'error', child: Text('Error')),
                      ],
                      onChanged: (value) {
                        if (value != null) {
                          setDialogState(() => selectedStatus = value);
                        }
                      },
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
                      await widget.apiClient.updateDocument(
                        token: widget.token,
                        companyId: widget.companyId,
                        documentId: document.id,
                        documentType: selectedType,
                        workflowStatus: selectedStatus,
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
                  child: const Text('Guardar'),
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
                    'Documentacion',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 8),
                  Text('Documentos cargados en ${widget.companyName}.'),
                ],
              ),
            ),
            FilledButton.icon(
              onPressed: _pickAndUpload,
              icon: const Icon(Icons.upload_file_rounded),
              label: const Text('Subir archivo'),
            ),
          ],
        ),
        const SizedBox(height: 24),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            SizedBox(
              width: 280,
              child: TextField(
                controller: _filenameController,
                decoration: const InputDecoration(
                  labelText: 'Buscar por nombre',
                ),
              ),
            ),
            SizedBox(
              width: 220,
              child: DropdownButtonFormField<String?>(
                value: _documentTypeFilter,
                decoration: const InputDecoration(labelText: 'Tipo documental'),
                items: const [
                  DropdownMenuItem<String?>(value: null, child: Text('Todos')),
                  DropdownMenuItem(
                    value: 'invoice_issued',
                    child: Text('Factura emitida'),
                  ),
                  DropdownMenuItem(
                    value: 'invoice_received',
                    child: Text('Factura recibida'),
                  ),
                  DropdownMenuItem(
                    value: 'bank_statement',
                    child: Text('Extracto bancario'),
                  ),
                  DropdownMenuItem(value: 'contract', child: Text('Contrato')),
                  DropdownMenuItem(
                    value: 'bank_receipt',
                    child: Text('Recibo bancario'),
                  ),
                  DropdownMenuItem(
                    value: 'unassigned',
                    child: Text('Sin asignar'),
                  ),
                  DropdownMenuItem(value: 'other', child: Text('Otro')),
                ],
                onChanged: (value) =>
                    setState(() => _documentTypeFilter = value),
              ),
            ),
            SizedBox(
              width: 220,
              child: DropdownButtonFormField<String?>(
                value: _workflowStatusFilter,
                decoration: const InputDecoration(labelText: 'Estado'),
                items: const [
                  DropdownMenuItem<String?>(value: null, child: Text('Todos')),
                  DropdownMenuItem(value: 'inbox', child: Text('Inbox')),
                  DropdownMenuItem(
                    value: 'classified',
                    child: Text('Clasificado'),
                  ),
                  DropdownMenuItem(
                    value: 'pending_review',
                    child: Text('Pendiente revision'),
                  ),
                  DropdownMenuItem(
                    value: 'pending_ocr',
                    child: Text('Pendiente OCR'),
                  ),
                  DropdownMenuItem(
                    value: 'pending_accounting',
                    child: Text('Pendiente contabilizar'),
                  ),
                  DropdownMenuItem(
                    value: 'accounted',
                    child: Text('Contabilizado'),
                  ),
                  DropdownMenuItem(value: 'archived', child: Text('Archivado')),
                  DropdownMenuItem(value: 'error', child: Text('Error')),
                ],
                onChanged: (value) =>
                    setState(() => _workflowStatusFilter = value),
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
                    child: Text('No hay documentos para la empresa activa.'),
                  )
                : ListView.separated(
                    itemCount: _items.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final item = _items[index];
                      return ListTile(
                        title: Text(item.originalFilename),
                        subtitle: Text(
                          '${item.documentType} · ${item.workflowStatus} · ${(item.fileSize / 1024).toStringAsFixed(1)} KB',
                        ),
                        trailing: IconButton(
                          onPressed: () => _openEditDialog(item),
                          icon: const Icon(Icons.edit_rounded),
                        ),
                      );
                    },
                  ),
          ),
        ),
      ],
    );
  }
}
