import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../../../core/sharing/android_share_receiver.dart';
import '../../auth/domain/user_profile.dart';
import '../../auth/presentation/auth_controller.dart';
import 'messaging_providers.dart';

class SharedSendResult {
  const SharedSendResult({required this.targetType, required this.targetId});

  final String targetType;
  final String targetId;
}

Future<SharedSendResult?> showShareTargetSheet({
  required BuildContext context,
  required SharedContent content,
}) {
  return showModalBottomSheet<SharedSendResult>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (_) => _ShareTargetSheet(content: content),
  );
}

class _ShareTarget {
  const _ShareTarget({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.internal,
  });

  final String id;
  final String title;
  final String subtitle;
  final bool internal;
}

class _ShareTargetSheet extends ConsumerStatefulWidget {
  const _ShareTargetSheet({required this.content});

  final SharedContent content;

  @override
  ConsumerState<_ShareTargetSheet> createState() => _ShareTargetSheetState();
}

class _ShareTargetSheetState extends ConsumerState<_ShareTargetSheet> {
  final _search = TextEditingController();
  late final Future<List<_ShareTarget>> _targets;
  _ShareTarget? _selected;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _targets = _loadTargets();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<List<_ShareTarget>> _loadTargets() async {
    final profile = ref.read(sessionProvider).valueOrNull!.profile;
    if (profile.type == UserType.client) {
      final conversations = await ref.read(conversationsProvider.future);
      return conversations
          .where((item) => item.organizationActive)
          .map(
            (item) => _ShareTarget(
              id: item.id,
              title: item.title,
              subtitle: item.displayChannelKind,
              internal: false,
            ),
          )
          .toList(growable: false);
    }
    final inbox = await ref.read(staffInboxProvider.future);
    return [
      for (final item in inbox.conversations.where(
        (item) => item.organizationActive,
      ))
        _ShareTarget(
          id: item.id,
          title: item.title,
          subtitle: '${item.companyCode} · ${item.displayChannelKind}',
          internal: false,
        ),
      for (final item in inbox.threads.where((item) => item.active))
        _ShareTarget(
          id: item.id,
          title: item.title,
          subtitle: item.kind == 'group' ? 'Grupo interno' : 'Chat interno',
          internal: true,
        ),
    ];
  }

  Future<void> _send() async {
    final target = _selected;
    if (target == null || _sending) return;
    setState(() => _sending = true);
    try {
      final repository = ref.read(messagingRepositoryProvider);
      if (target.internal) {
        await repository.sendInternal(target.id, '', widget.content.files);
      } else {
        final profile = ref.read(sessionProvider).valueOrNull!.profile;
        await repository.send(profile, target.id, '', widget.content.files);
      }
      if (!mounted) return;
      Navigator.pop(
        context,
        SharedSendResult(
          targetType: target.internal ? 'internal_thread' : 'conversation',
          targetId: target.id,
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
        setState(() => _sending = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.viewInsetsOf(context).bottom;
    final bottomPadding = MediaQuery.paddingOf(context).bottom;
    return FractionallySizedBox(
      heightFactor: 0.9,
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          16,
          8,
          16,
          16 + bottomInset + bottomPadding,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Compartir con Gestinem',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            _SharedFilesSummary(files: widget.content.files),
            const SizedBox(height: 12),
            TextField(
              key: const Key('share-target-search'),
              controller: _search,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Buscar conversación',
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: FutureBuilder<List<_ShareTarget>>(
                future: _targets,
                builder: (context, snapshot) {
                  if (snapshot.connectionState != ConnectionState.done) {
                    return const Center(child: CircularProgressIndicator());
                  }
                  if (snapshot.hasError) {
                    return Center(
                      child: Text(apiErrorMessage(snapshot.error!)),
                    );
                  }
                  final query = _search.text.trim().toLowerCase();
                  final targets = (snapshot.data ?? const <_ShareTarget>[])
                      .where(
                        (item) =>
                            query.isEmpty ||
                            item.title.toLowerCase().contains(query) ||
                            item.subtitle.toLowerCase().contains(query),
                      )
                      .toList(growable: false);
                  if (targets.isEmpty) {
                    return const Center(
                      child: Text('No hay conversaciones disponibles.'),
                    );
                  }
                  return ListView.builder(
                    itemCount: targets.length,
                    itemBuilder: (context, index) {
                      final target = targets[index];
                      final selected =
                          _selected?.id == target.id &&
                          _selected?.internal == target.internal;
                      return ListTile(
                        key: Key(
                          'share-target-${target.internal ? 'internal' : 'conversation'}-${target.id}',
                        ),
                        selected: selected,
                        onTap: _sending
                            ? null
                            : () => setState(() => _selected = target),
                        leading: Icon(
                          target.internal
                              ? Icons.groups_outlined
                              : Icons.business_outlined,
                        ),
                        title: Text(target.title),
                        subtitle: Text(target.subtitle),
                        trailing: selected
                            ? const Icon(Icons.check_circle)
                            : const Icon(Icons.circle_outlined),
                      );
                    },
                  );
                },
              ),
            ),
            const SizedBox(height: 8),
            FilledButton.icon(
              key: const Key('send-shared-files'),
              onPressed: _selected == null || _sending ? null : _send,
              icon: _sending
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.send_outlined),
              label: Text(_sending ? 'Enviando…' : 'Enviar'),
            ),
          ],
        ),
      ),
    );
  }
}

class _SharedFilesSummary extends StatelessWidget {
  const _SharedFilesSummary({required this.files});

  final List<PlatformFile> files;

  @override
  Widget build(BuildContext context) {
    final first = files.first;
    final extra = files.length - 1;
    return Card(
      child: ListTile(
        leading: const Icon(Icons.attach_file),
        title: Text(first.name, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: Text(
          extra > 0
              ? '${files.length} archivos seleccionados'
              : 'Listo para enviar',
        ),
      ),
    );
  }
}
