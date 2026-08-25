import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../domain/client_document.dart';
import 'documents_providers.dart';

/// Pantalla de listado de documentos del area del cliente.
class DocumentsScreen extends ConsumerWidget {
  const DocumentsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final docsAsync = ref.watch(documentsProvider);
    final fiscalYear = ref.watch(documentsFiscalYearProvider);
    final currentYear = DateTime.now().year;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Mis documentos'),
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
                  child: Text(
                    '$y${y == fiscalYear ? ' ✓' : ''}',
                  ),
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
          if (response.items.isEmpty) {
            return const Center(
              child: Text('No hay documentos para este ejercicio.'),
            );
          }
          return ListView.builder(
            itemCount: response.items.length,
            itemBuilder: (context, index) {
              final doc = response.items[index];
              return _DocumentTile(document: doc);
            },
          );
        },
      ),
    );
  }
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
          if (document.amount != null) '${document.amount} ${document.currency}',
          if (document.isReplaced) 'Sustituida',
          if (document.isWithdrawn) 'Retirada',
        ].join(' · '),
      ),
      trailing: document.isPublished
          ? const Icon(Icons.chevron_right)
          : null,
      onTap: () => context.push('/documents/${document.id}'),
    );
  }
}
