import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/api/api_client.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/invitation_content.dart';
import 'messaging_providers.dart';

class InvitationContentScreen extends ConsumerStatefulWidget {
  const InvitationContentScreen({super.key});

  @override
  ConsumerState<InvitationContentScreen> createState() =>
      _InvitationContentScreenState();
}

class _InvitationContentScreenState
    extends ConsumerState<InvitationContentScreen> {
  final _subject = TextEditingController();
  final _intro = TextEditingController();
  final _closing = TextEditingController();
  InvitationContentConfiguration? _configuration;
  List<InvitationContentVersion> _history = const [];
  bool _loading = true;
  bool _working = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _subject.dispose();
    _intro.dispose();
    _closing.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repository = ref.read(messagingRepositoryProvider);
      final configuration = await repository.invitationContent();
      final history = await repository.invitationContentHistory();
      if (!mounted) return;
      _configuration = configuration;
      _history = history;
      _apply(configuration.editable);
    } catch (error) {
      if (mounted) setState(() => _error = apiErrorMessage(error));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _apply(InvitationContentVersion content) {
    _subject.text = content.subject;
    _intro.text = content.introText;
    _closing.text = content.closingText;
  }

  bool _validate() {
    if (_subject.text.trim().isEmpty ||
        _intro.text.trim().isEmpty ||
        _closing.text.trim().isEmpty) {
      setState(
        () => _error = 'Completa el asunto y los dos bloques del correo.',
      );
      return false;
    }
    return true;
  }

  Future<InvitationContentVersion?> _saveDraft({bool notify = true}) async {
    if (!_validate()) return null;
    setState(() {
      _working = true;
      _error = null;
    });
    try {
      final draft = await ref
          .read(messagingRepositoryProvider)
          .saveInvitationDraft(
            subject: _subject.text.trim(),
            introText: _intro.text.trim(),
            closingText: _closing.text.trim(),
          );
      if (!mounted) return draft;
      if (notify) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Borrador guardado.')));
      }
      return draft;
    } catch (error) {
      if (mounted) setState(() => _error = apiErrorMessage(error));
      return null;
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _pickManual() async {
    List<PlatformFile> files;
    try {
      files = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['pdf'],
      );
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'No se pudo abrir el selector de archivos.');
      }
      return;
    }
    if (files.isEmpty || await _saveDraft(notify: false) == null || !mounted) {
      return;
    }
    setState(() => _working = true);
    try {
      await ref
          .read(messagingRepositoryProvider)
          .uploadInvitationManual(files.first);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Manual cargado en el borrador. Publícalo para activarlo.',
          ),
        ),
      );
      await _load();
    } catch (error) {
      if (mounted) setState(() => _error = apiErrorMessage(error));
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _preview() async {
    if (!_validate()) return;
    setState(() => _working = true);
    try {
      final preview = await ref
          .read(messagingRepositoryProvider)
          .previewInvitationContent(
            subject: _subject.text.trim(),
            introText: _intro.text.trim(),
            closingText: _closing.text.trim(),
          );
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(preview['subject'] as String? ?? 'Vista previa'),
          content: SizedBox(
            width: 680,
            child: SingleChildScrollView(
              child: SelectableText(preview['text'] as String? ?? ''),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cerrar'),
            ),
          ],
        ),
      );
    } catch (error) {
      if (mounted) setState(() => _error = apiErrorMessage(error));
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _sendTest() async {
    if (await _saveDraft(notify: false) == null || !mounted) return;
    setState(() => _working = true);
    try {
      final email = await ref
          .read(messagingRepositoryProvider)
          .sendInvitationTest();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Correo de prueba enviado a $email.')),
      );
    } catch (error) {
      if (mounted) setState(() => _error = apiErrorMessage(error));
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _publish() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Publicar invitación'),
        content: const Text(
          'Las próximas invitaciones utilizarán inmediatamente este texto y este manual.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            key: const Key('publish-invitation-content-confirm'),
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Publicar'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    if (await _saveDraft(notify: false) == null || !mounted) return;
    setState(() => _working = true);
    try {
      final published = await ref
          .read(messagingRepositoryProvider)
          .publishInvitationContent();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Versión ${published.version} publicada.')),
      );
      await _load();
    } catch (error) {
      if (mounted) setState(() => _error = apiErrorMessage(error));
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _restore(InvitationContentVersion version) async {
    setState(() => _working = true);
    try {
      await ref
          .read(messagingRepositoryProvider)
          .restoreInvitationContent(version.id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Versión ${version.version} recuperada como borrador.'),
        ),
      );
      await _load();
    } catch (error) {
      if (mounted) setState(() => _error = apiErrorMessage(error));
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _openManual() async {
    final url = _configuration?.manualUrl ?? '';
    if (url.isEmpty ||
        !await launchUrl(
          Uri.parse(url),
          mode: LaunchMode.externalApplication,
        )) {
      if (mounted) setState(() => _error = 'No se pudo abrir el manual.');
    }
  }

  String _size(int bytes) {
    if (bytes <= 0) return 'manual incluido inicialmente';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  String _date(DateTime? value) {
    if (value == null) return '';
    final local = value.toLocal();
    String two(int number) => number.toString().padLeft(2, '0');
    return '${two(local.day)}/${two(local.month)}/${local.year} '
        '${two(local.hour)}:${two(local.minute)}';
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    if (!profile.isAdmin) {
      return const Scaffold(
        body: Center(
          child: Text('Solo el administrador puede configurar invitaciones.'),
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          tooltip: 'Volver',
          onPressed: () => context.pop(),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Invitación de clientes'),
        actions: [
          IconButton(
            tooltip: 'Actualizar',
            onPressed: _working ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _configuration == null
          ? Center(child: Text(_error ?? 'No se pudo cargar la configuración.'))
          : AbsorbPointer(
              absorbing: _working,
              child: Stack(
                children: [
                  ListView(
                    padding: const EdgeInsets.all(20),
                    children: [
                      _statusCard(),
                      const SizedBox(height: 16),
                      if (_error != null)
                        Card(
                          color: Theme.of(context).colorScheme.errorContainer,
                          child: Padding(
                            padding: const EdgeInsets.all(14),
                            child: Text(
                              _error!,
                              style: TextStyle(
                                color: Theme.of(
                                  context,
                                ).colorScheme.onErrorContainer,
                              ),
                            ),
                          ),
                        ),
                      TextField(
                        key: const Key('invitation-subject'),
                        controller: _subject,
                        maxLength: 300,
                        decoration: const InputDecoration(
                          labelText: 'Asunto',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 12),
                      _variablesHelp(),
                      const SizedBox(height: 12),
                      TextField(
                        key: const Key('invitation-intro'),
                        controller: _intro,
                        minLines: 8,
                        maxLines: 18,
                        decoration: const InputDecoration(
                          labelText: 'Texto anterior a los enlaces',
                          alignLabelWithHint: true,
                          border: OutlineInputBorder(),
                          helperText:
                              'Después de este bloque aparecerán los botones de activación y del manual.',
                        ),
                      ),
                      const SizedBox(height: 20),
                      _protectedLinksCard(),
                      const SizedBox(height: 20),
                      TextField(
                        key: const Key('invitation-closing'),
                        controller: _closing,
                        minLines: 8,
                        maxLines: 18,
                        decoration: const InputDecoration(
                          labelText: 'Texto posterior a los enlaces',
                          alignLabelWithHint: true,
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 20),
                      _manualCard(),
                      const SizedBox(height: 20),
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: [
                          OutlinedButton.icon(
                            key: const Key('preview-invitation-content'),
                            onPressed: _preview,
                            icon: const Icon(Icons.preview_outlined),
                            label: const Text('Vista previa'),
                          ),
                          OutlinedButton.icon(
                            key: const Key('test-invitation-content'),
                            onPressed: _sendTest,
                            icon: const Icon(Icons.mark_email_read_outlined),
                            label: const Text('Enviar prueba a mi correo'),
                          ),
                          FilledButton.tonalIcon(
                            key: const Key('save-invitation-content'),
                            onPressed: _saveDraft,
                            icon: const Icon(Icons.save_outlined),
                            label: const Text('Guardar borrador'),
                          ),
                          FilledButton.icon(
                            key: const Key('publish-invitation-content'),
                            onPressed: _publish,
                            icon: const Icon(Icons.publish_outlined),
                            label: const Text('Publicar'),
                          ),
                        ],
                      ),
                      const SizedBox(height: 28),
                      _historyCard(),
                      const SizedBox(height: 40),
                    ],
                  ),
                  if (_working)
                    const Positioned(
                      top: 8,
                      left: 20,
                      right: 20,
                      child: LinearProgressIndicator(),
                    ),
                ],
              ),
            ),
    );
  }

  Widget _statusCard() {
    final configuration = _configuration!;
    final active = configuration.active;
    return Card(
      child: ListTile(
        leading: const Icon(Icons.check_circle_outline, color: Colors.green),
        title: Text(
          active.version == 0
              ? 'Contenido inicial publicado'
              : 'Versión ${active.version} publicada',
        ),
        subtitle: Text(
          configuration.draft == null
              ? 'No hay cambios pendientes.'
              : 'Hay un borrador pendiente de publicar.',
        ),
        trailing: configuration.draft == null
            ? null
            : const Chip(label: Text('BORRADOR')),
      ),
    );
  }

  Widget _variablesHelp() => Card(
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Variables disponibles',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final variable in _configuration!.allowedVariables)
                Chip(label: SelectableText(variable)),
            ],
          ),
        ],
      ),
    ),
  );

  Widget _protectedLinksCard() => Card(
    color: Theme.of(context).colorScheme.primaryContainer,
    child: const Padding(
      padding: EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Enlaces protegidos',
            style: TextStyle(fontWeight: FontWeight.bold),
          ),
          SizedBox(height: 8),
          Text('• Activar mi cuenta y acceder a Gestinem'),
          Text('• Consultar el manual de Gestinem'),
          SizedBox(height: 8),
          Text(
            'El sistema incorpora siempre estos enlaces y también muestra la dirección de activación en texto plano.',
          ),
        ],
      ),
    ),
  );

  Widget _manualCard() {
    final manual = _configuration!.editable;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Manual de clientes',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text('${manual.manualName} · ${_size(manual.manualSize)}'),
            const SizedBox(height: 4),
            SelectableText(_configuration!.manualUrl),
            const SizedBox(height: 12),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                OutlinedButton.icon(
                  onPressed: _openManual,
                  icon: const Icon(Icons.open_in_new),
                  label: const Text('Abrir manual publicado'),
                ),
                FilledButton.tonalIcon(
                  key: const Key('upload-invitation-manual'),
                  onPressed: _pickManual,
                  icon: const Icon(Icons.upload_file),
                  label: const Text('Sustituir PDF'),
                ),
              ],
            ),
            const SizedBox(height: 8),
            const Text(
              'El PDF no se adjunta al correo. Este enlace estable mostrará siempre la versión publicada más reciente.',
            ),
          ],
        ),
      ),
    );
  }

  Widget _historyCard() => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Historial', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          if (_history.isEmpty)
            const Text(
              'El contenido inicial todavía no tiene versiones publicadas.',
            )
          else
            for (final version in _history)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: CircleAvatar(child: Text('${version.version}')),
                title: Text(version.subject),
                subtitle: Text(
                  '${_date(version.publishedAt)} · ${version.manualName}',
                ),
                trailing: version.status == 'published'
                    ? const Chip(label: Text('ACTIVA'))
                    : TextButton(
                        onPressed: () => _restore(version),
                        child: const Text('Recuperar'),
                      ),
              ),
        ],
      ),
    ),
  );
}
