import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../../core/models/document_model.dart';
import '../../../core/models/document_ocr_result_model.dart';
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
  String? _busyDocumentId;

  static const List<_DocumentTypeOption> _documentTypeOptions = [
    _DocumentTypeOption('invoice_issued', 'Factura emitida'),
    _DocumentTypeOption('invoice_received', 'Factura recibida'),
    _DocumentTypeOption('bank_statement', 'Extracto bancario'),
    _DocumentTypeOption('contract', 'Contrato'),
    _DocumentTypeOption('bank_receipt', 'Recibo bancario'),
    _DocumentTypeOption('unassigned', 'Sin asignar'),
    _DocumentTypeOption('other', 'Otro'),
  ];

  static const List<_WorkflowStatusOption> _workflowOptions = [
    _WorkflowStatusOption('inbox', 'Inbox'),
    _WorkflowStatusOption('classified', 'Clasificado'),
    _WorkflowStatusOption('pending_review', 'Pendiente revision'),
    _WorkflowStatusOption('pending_ocr', 'Pendiente OCR'),
    _WorkflowStatusOption('pending_accounting', 'Pendiente contabilizar'),
    _WorkflowStatusOption('batched', 'En lote'),
    _WorkflowStatusOption('exported', 'Exportado'),
    _WorkflowStatusOption('archived', 'Archivado'),
    _WorkflowStatusOption('error', 'Error'),
  ];

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

  Future<void> _runOcr(DocumentModel document) async {
    setState(() => _busyDocumentId = document.id);
    try {
      final result = await widget.apiClient.runDocumentOcr(
        token: widget.token,
        companyId: widget.companyId,
        documentId: document.id,
      );
      if (!mounted) return;
      await _load();
      if (!mounted) return;
      await _showOcrResult(document, initialResult: result);
    } on ApiException catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(exc.message)));
    } finally {
      if (mounted) {
        setState(() => _busyDocumentId = null);
      }
    }
  }

  Future<void> _showOcrResult(
    DocumentModel document, {
    DocumentOcrResultModel? initialResult,
  }) async {
    try {
      final result =
          initialResult ??
          await widget.apiClient.getDocumentOcrResult(
            token: widget.token,
            companyId: widget.companyId,
            documentId: document.id,
          );
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) {
          return AlertDialog(
            title: Text('OCR ${document.originalFilename}'),
            content: SizedBox(
              width: 720,
              child: SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Wrap(
                      spacing: 12,
                      runSpacing: 12,
                      children: [
                        _InfoChip(
                          label: 'Estado OCR',
                          value: _formatOcrStatus(result.status),
                        ),
                        _InfoChip(
                          label: 'Confianza',
                          value: result.confidence == null
                              ? '-'
                              : '${(result.confidence! * 100).toStringAsFixed(0)}%',
                        ),
                        _InfoChip(
                          label: 'Sugerencia',
                          value: _formatDocumentType(
                            result.extractedData['document_type_suggestion']
                                    as String? ??
                                'unassigned',
                          ),
                        ),
                      ],
                    ),
                    if (result.errorMessage != null) ...[
                      const SizedBox(height: 16),
                      Text(
                        result.errorMessage!,
                        style: const TextStyle(color: Colors.redAccent),
                      ),
                    ],
                    const SizedBox(height: 16),
                    const Text(
                      'Texto OCR',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 8),
                    Container(
                      width: double.infinity,
                      constraints: const BoxConstraints(maxHeight: 360),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF7F9FC),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFFD8E0E8)),
                      ),
                      child: SelectableText(
                        result.extractedText?.trim().isNotEmpty == true
                            ? result.extractedText!
                            : 'No hay texto OCR disponible.',
                      ),
                    ),
                  ],
                ),
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text('Cerrar'),
              ),
            ],
          );
        },
      );
    } on ApiException catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(exc.message)));
    }
  }

  Future<void> _classifyDocument(DocumentModel document) async {
    String selectedType = document.documentType;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (dialogContext, setDialogState) {
            return AlertDialog(
              title: Text('Clasificar ${document.originalFilename}'),
              content: SizedBox(
                width: 420,
                child: DropdownButtonFormField<String>(
                  initialValue: selectedType,
                  decoration: const InputDecoration(
                    labelText: 'Tipo documental',
                  ),
                  items: _documentTypeOptions
                      .map(
                        (option) => DropdownMenuItem(
                          value: option.value,
                          child: Text(option.label),
                        ),
                      )
                      .toList(),
                  onChanged: (value) {
                    if (value != null) {
                      setDialogState(() => selectedType = value);
                    }
                  },
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
                      await widget.apiClient.classifyDocument(
                        token: widget.token,
                        companyId: widget.companyId,
                        documentId: document.id,
                        documentType: selectedType,
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
                      initialValue: selectedType,
                      decoration: const InputDecoration(
                        labelText: 'Tipo documental',
                      ),
                      items: _documentTypeOptions
                          .map(
                            (option) => DropdownMenuItem(
                              value: option.value,
                              child: Text(option.label),
                            ),
                          )
                          .toList(),
                      onChanged: (value) {
                        if (value != null) {
                          setDialogState(() => selectedType = value);
                        }
                      },
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: selectedStatus,
                      decoration: const InputDecoration(
                        labelText: 'Estado de workflow',
                      ),
                      items: _workflowOptions
                          .map(
                            (option) => DropdownMenuItem(
                              value: option.value,
                              child: Text(option.label),
                            ),
                          )
                          .toList(),
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
                initialValue: _documentTypeFilter,
                decoration: const InputDecoration(labelText: 'Tipo documental'),
                items: [
                  const DropdownMenuItem<String?>(
                    value: null,
                    child: Text('Todos'),
                  ),
                  ..._documentTypeOptions.map(
                    (option) => DropdownMenuItem<String?>(
                      value: option.value,
                      child: Text(option.label),
                    ),
                  ),
                ],
                onChanged: (value) =>
                    setState(() => _documentTypeFilter = value),
              ),
            ),
            SizedBox(
              width: 220,
              child: DropdownButtonFormField<String?>(
                initialValue: _workflowStatusFilter,
                decoration: const InputDecoration(labelText: 'Estado'),
                items: [
                  const DropdownMenuItem<String?>(
                    value: null,
                    child: Text('Todos'),
                  ),
                  ..._workflowOptions.map(
                    (option) => DropdownMenuItem<String?>(
                      value: option.value,
                      child: Text(option.label),
                    ),
                  ),
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
                      final isBusy = _busyDocumentId == item.id;
                      final ocrStatus = item.ocrResult?.status;
                      return ListTile(
                        title: Text(item.originalFilename),
                        subtitle: Text(
                          '${_formatDocumentType(item.documentType)} · ${_formatWorkflowStatus(item.workflowStatus)} · OCR ${_formatOcrStatus(ocrStatus)} · ${(item.fileSize / 1024).toStringAsFixed(1)} KB',
                        ),
                        trailing: Wrap(
                          spacing: 4,
                          children: [
                            IconButton(
                              tooltip: 'Clasificar',
                              onPressed: isBusy
                                  ? null
                                  : () => _classifyDocument(item),
                              icon: const Icon(Icons.category_rounded),
                            ),
                            IconButton(
                              tooltip: 'Ejecutar OCR',
                              onPressed: isBusy ? null : () => _runOcr(item),
                              icon: isBusy
                                  ? const SizedBox(
                                      width: 18,
                                      height: 18,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.text_snippet_rounded),
                            ),
                            IconButton(
                              tooltip: 'Ver OCR',
                              onPressed: item.ocrResult == null || isBusy
                                  ? null
                                  : () => _showOcrResult(item),
                              icon: const Icon(Icons.visibility_rounded),
                            ),
                            IconButton(
                              tooltip: 'Editar',
                              onPressed: isBusy
                                  ? null
                                  : () => _openEditDialog(item),
                              icon: const Icon(Icons.edit_rounded),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
        ),
      ],
    );
  }

  String _formatDocumentType(String value) {
    return _documentTypeOptions
        .firstWhere(
          (option) => option.value == value,
          orElse: () => const _DocumentTypeOption('unknown', 'Desconocido'),
        )
        .label;
  }

  String _formatWorkflowStatus(String value) {
    return _workflowOptions
        .firstWhere(
          (option) => option.value == value,
          orElse: () => const _WorkflowStatusOption('unknown', 'Desconocido'),
        )
        .label;
  }

  String _formatOcrStatus(String? value) {
    switch (value) {
      case 'pending':
        return 'Pendiente';
      case 'processed':
        return 'Procesado';
      case 'reviewed':
        return 'Revisado';
      case 'error':
        return 'Error';
      case null:
        return 'Sin OCR';
      default:
        return value;
    }
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFF7F9FC),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFD8E0E8)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: const TextStyle(fontSize: 12, color: Color(0xFF5C6B7A)),
          ),
          const SizedBox(height: 4),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

class _DocumentTypeOption {
  const _DocumentTypeOption(this.value, this.label);

  final String value;
  final String label;
}

class _WorkflowStatusOption {
  const _WorkflowStatusOption(this.value, this.label);

  final String value;
  final String label;
}
