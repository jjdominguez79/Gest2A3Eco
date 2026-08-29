import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../domain/client_document.dart';
import '../../platform/features_provider.dart';
import 'documents_providers.dart';

/// Pantalla de listado de documentos del area del cliente.
class DocumentsScreen extends ConsumerWidget {
  const DocumentsScreen({super.key, this.folderKey});

  final String? folderKey;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final featuresAsync = ref.watch(platformFeaturesProvider);
    final features = featuresAsync.valueOrNull;
    if (features != null && !features.documents) {
      return Scaffold(
        appBar: AppBar(title: const Text('Mis documentos')),
        body: const Center(
          child: Text('El area documental no esta habilitada.'),
        ),
      );
    }

    final docsAsync = ref.watch(documentsProvider);
    final fiscalYear = ref.watch(documentsFiscalYearProvider);
    final currentYear = DateTime.now().year;
    final selectedFolder = folderKey == null
        ? null
        : DocumentFolder.fromKey(folderKey!);

    return Scaffold(
      appBar: AppBar(
        title: Text(selectedFolder?.label ?? 'Mis documentos'),
        actions: [
          // Selector de ejercicio
          PopupMenuButton<int>(
            icon: const Icon(Icons.calendar_today),
            tooltip: 'Ejercicio',
            onSelected: (year) {
              ref.read(documentsFiscalYearProvider.notifier).state = year;
            },
            itemBuilder: (_) => [
              for (var y = currentYear; y >= currentYear - 4; y--)
                PopupMenuItem(
                  value: y,
                  child: Text('$y${y == fiscalYear ? ' ✓' : ''}'),
                ),
            ],
          ),
        ],
      ),
      body: docsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Error: $error'),
              const SizedBox(height: 8),
              ElevatedButton(
                onPressed: () => ref.invalidate(documentsProvider),
                child: const Text('Reintentar'),
              ),
            ],
          ),
        ),
        data: (response) {
          if (selectedFolder == null) {
            return _FolderGrid(documents: response.items);
          }
          final documents = response.items
              .where((document) => document.folder == selectedFolder)
              .toList();
          if (documents.isEmpty) {
            return Center(
              child: Text(
                'No hay documentos en ${selectedFolder.label.toLowerCase()} '
                'para este ejercicio.',
              ),
            );
          }
          return ListView.builder(
            itemCount: documents.length,
            itemBuilder: (context, index) {
              final doc = documents[index];
              return _DocumentTile(document: doc);
            },
          );
        },
      ),
    );
  }
}

class _FolderGrid extends StatelessWidget {
  const _FolderGrid({required this.documents});

  final List<ClientDocument> documents;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final columns = width >= 900
        ? 3
        : width >= 560
        ? 2
        : 1;
    return GridView.builder(
      padding: const EdgeInsets.all(16),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: columns,
        mainAxisExtent: 112,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
      ),
      itemCount: DocumentFolder.values.length,
      itemBuilder: (context, index) {
        final folder = DocumentFolder.values[index];
        final folderDocuments = documents
            .where((document) => document.folder == folder)
            .toList();
        final unread = folderDocuments
            .where((document) => document.isPublished && !document.isRead)
            .length;
        return Card(
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: () => context.push('/documents/folder/${folder.key}'),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
              child: Row(
                children: [
                  Icon(
                    _folderIcon(folder),
                    size: 38,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          folder.label,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${folderDocuments.length} documento${folderDocuments.length == 1 ? '' : 's'}',
                        ),
                      ],
                    ),
                  ),
                  if (unread > 0)
                    Badge(label: Text('$unread'))
                  else
                    const Icon(Icons.chevron_right),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  IconData _folderIcon(DocumentFolder folder) => switch (folder) {
    DocumentFolder.facturas => Icons.receipt_long_outlined,
    DocumentFolder.certificados => Icons.workspace_premium_outlined,
    DocumentFolder.nominas => Icons.badge_outlined,
    DocumentFolder.impuestos => Icons.account_balance_outlined,
    DocumentFolder.contratos => Icons.handshake_outlined,
    DocumentFolder.otros => Icons.folder_outlined,
  };
}

class _DocumentTile extends StatelessWidget {
  const _DocumentTile({required this.document});

  final ClientDocument document;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isUnread = !document.isRead && document.isPublished;

    return ListTile(
      leading: Stack(
        children: [
          Icon(
            document.isWithdrawn
                ? Icons.block
                : document.isReplaced
                ? Icons.swap_horiz
                : Icons.description,
            color: document.isWithdrawn
                ? theme.colorScheme.error
                : document.isReplaced
                ? Colors.orange
                : null,
          ),
          if (isUnread)
            Positioned(
              right: 0,
              top: 0,
              child: Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: theme.colorScheme.primary,
                  shape: BoxShape.circle,
                ),
              ),
            ),
        ],
      ),
      title: Text(
        document.displayName,
        style: isUnread
            ? theme.textTheme.bodyLarge?.copyWith(fontWeight: FontWeight.bold)
            : null,
      ),
      subtitle: Text(
        [
          if (document.documentDate != null)
            document.documentDate!.substring(0, 10),
          if (document.amount != null)
            '${document.amount} ${document.currency}',
          if (document.isReplaced) 'Sustituida',
          if (document.isWithdrawn) 'Retirada',
        ].join(' · '),
      ),
      trailing: document.isPublished ? const Icon(Icons.chevron_right) : null,
      onTap: () => context.push('/documents/${document.id}'),
    );
  }
}
