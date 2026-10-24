import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/api/api_client.dart';
import '../domain/dgt_expediente.dart';
import 'dgt_providers.dart';

String normalizarTelefonoWhatsAppDgt(String value) {
  var digits = value.replaceAll(RegExp(r'\D'), '');
  if (digits.startsWith('00')) digits = digits.substring(2);
  if (digits.length == 9) digits = '34$digits';
  return digits;
}

class DgtScreen extends ConsumerStatefulWidget {
  const DgtScreen({super.key});

  @override
  ConsumerState<DgtScreen> createState() => _DgtScreenState();
}

class _DgtScreenState extends ConsumerState<DgtScreen> {
  bool _procesando = false;

  Future<void> _crear() async {
    final data = await showDialog<_NuevoDgtData>(
      context: context,
      builder: (_) => const _NuevoDgtDialog(),
    );
    if (data == null || !mounted) return;
    setState(() => _procesando = true);
    try {
      final created = await ref
          .read(dgtRepositoryProvider)
          .crear(
            titulo: data.titulo,
            vendedorNombre: data.vendedorNombre,
            vendedorTelefono: data.vendedorTelefono,
            compradorNombre: data.compradorNombre,
            compradorTelefono: data.compradorTelefono,
          );
      ref.invalidate(expedientesDgtProvider);
      if (mounted) {
        await _mostrarEnlaces(created.expediente, created.enlaces);
      }
    } catch (error) {
      _mostrarError(error);
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  Future<void> _regenerar(DgtExpediente expediente) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Generar enlaces nuevos'),
        content: const Text(
          'Los enlaces anteriores dejarán de funcionar. Tendrás que enviar '
          'los dos enlaces nuevos.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Generar'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _procesando = true);
    try {
      final links = await ref
          .read(dgtRepositoryProvider)
          .generarEnlaces(expediente.id);
      ref.invalidate(expedientesDgtProvider);
      if (mounted) await _mostrarEnlaces(expediente, links);
    } catch (error) {
      _mostrarError(error);
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  Future<void> _comprobar(DgtExpediente expediente) async {
    setState(() => _procesando = true);
    try {
      final result = await ref
          .read(dgtRepositoryProvider)
          .comprobar(expediente.id);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Row(
            children: [
              Icon(
                result.completo ? Icons.check_circle : Icons.warning_amber,
                color: result.completo ? Colors.green : Colors.orange,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  result.completo ? 'Expediente completo' : 'Datos pendientes',
                ),
              ),
            ],
          ),
          content: SizedBox(
            width: 560,
            child: result.completo
                ? const Text(
                    'El vendedor y el comprador han enviado todos los datos '
                    'necesarios y la documentación exigible está aportada.',
                  )
                : SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Text(
                          'Falta completar lo siguiente antes de continuar:',
                        ),
                        const SizedBox(height: 12),
                        for (final error in result.errores)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text('•  '),
                                Expanded(child: Text(error)),
                              ],
                            ),
                          ),
                      ],
                    ),
                  ),
          ),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cerrar'),
            ),
          ],
        ),
      );
    } catch (error) {
      _mostrarError(error);
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  Future<void> _mostrarEnlaces(
    DgtExpediente expediente,
    Map<String, DgtEnlace> enlaces,
  ) async {
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => AlertDialog(
        title: Text('Enlaces ${expediente.referencia}'),
        content: SizedBox(
          width: 560,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'Envía cada enlace a la persona correcta. Los enlaces '
                  'contienen acceso privado a su formulario.',
                ),
                const SizedBox(height: 12),
                for (final rol in const ['vendedor', 'comprador'])
                  if (enlaces[rol] != null)
                    _EnlaceCard(
                      expediente: expediente,
                      enlace: enlaces[rol]!,
                      onWhatsApp: () =>
                          _enviarWhatsApp(expediente, enlaces[rol]!),
                    ),
              ],
            ),
          ),
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('He terminado'),
          ),
        ],
      ),
    );
  }

  Future<void> _enviarWhatsApp(
    DgtExpediente expediente,
    DgtEnlace enlace,
  ) async {
    final parte = expediente.partes[enlace.rol];
    final nombre = parte?.nombre.trim() ?? '';
    final saludo = nombre.isEmpty ? 'Hola' : 'Hola $nombre';
    final mensaje =
        '$saludo, puedes completar los datos del expediente DGT '
        '${expediente.referencia} en este enlace:\n${enlace.url}';
    final telefono = normalizarTelefonoWhatsAppDgt(parte?.telefono ?? '');
    if (telefono.isNotEmpty) {
      final uri = Uri.https('wa.me', '/$telefono', {'text': mensaje});
      if (await launchUrl(uri, mode: LaunchMode.externalApplication)) return;
    }
    await SharePlus.instance.share(ShareParams(text: mensaje));
  }

  void _mostrarError(Object error) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
  }

  @override
  Widget build(BuildContext context) {
    final expedientes = ref.watch(expedientesDgtProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Trámites DGT'),
        actions: [
          IconButton(
            key: const Key('dgt-refrescar'),
            tooltip: 'Actualizar',
            onPressed: _procesando
                ? null
                : () => ref.invalidate(expedientesDgtProvider),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Stack(
        children: [
          expedientes.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (error, _) => Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(apiErrorMessage(error), textAlign: TextAlign.center),
                    const SizedBox(height: 12),
                    FilledButton.icon(
                      onPressed: () => ref.invalidate(expedientesDgtProvider),
                      icon: const Icon(Icons.refresh),
                      label: const Text('Reintentar'),
                    ),
                  ],
                ),
              ),
            ),
            data: (items) => items.isEmpty
                ? const _DgtVacio()
                : RefreshIndicator(
                    onRefresh: () => ref.refresh(expedientesDgtProvider.future),
                    child: ListView.builder(
                      padding: const EdgeInsets.fromLTRB(12, 12, 12, 96),
                      itemCount: items.length,
                      itemBuilder: (_, index) => _ExpedienteCard(
                        expediente: items[index],
                        onLinks: () => _regenerar(items[index]),
                        onCheck: () => _comprobar(items[index]),
                      ),
                    ),
                  ),
          ),
          if (_procesando)
            const Positioned.fill(
              child: ColoredBox(
                color: Color(0x33000000),
                child: Center(child: CircularProgressIndicator()),
              ),
            ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('dgt-nuevo'),
        onPressed: _procesando ? null : _crear,
        icon: const Icon(Icons.add),
        label: const Text('Nuevo expediente'),
      ),
    );
  }
}

class _DgtVacio extends StatelessWidget {
  const _DgtVacio();

  @override
  Widget build(BuildContext context) => const Center(
    child: Padding(
      padding: EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.directions_car_outlined, size: 56),
          SizedBox(height: 12),
          Text('Todavía no hay expedientes DGT.'),
          SizedBox(height: 4),
          Text('Crea uno para generar los enlaces de ambas partes.'),
        ],
      ),
    ),
  );
}

class _ExpedienteCard extends StatelessWidget {
  const _ExpedienteCard({
    required this.expediente,
    required this.onLinks,
    required this.onCheck,
  });

  final DgtExpediente expediente;
  final VoidCallback onLinks;
  final VoidCallback onCheck;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 10),
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      expediente.referencia,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    Text(
                      expediente.titulo,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              _EstadoChip(expediente.estado),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              for (final rol in const ['vendedor', 'comprador'])
                _ParteChip(parte: expediente.partes[rol]!),
              if (expediente.matricula.isNotEmpty)
                Chip(
                  avatar: const Icon(Icons.directions_car, size: 18),
                  label: Text(expediente.matricula),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              OutlinedButton.icon(
                key: Key('dgt-comprobar-${expediente.id}'),
                onPressed: onCheck,
                icon: const Icon(Icons.fact_check_outlined),
                label: const Text('Comprobar datos'),
              ),
              FilledButton.tonalIcon(
                key: Key('dgt-enlaces-${expediente.id}'),
                onPressed: onLinks,
                icon: const Icon(Icons.share_outlined),
                label: const Text('Nuevos enlaces'),
              ),
            ],
          ),
        ],
      ),
    ),
  );
}

class _EstadoChip extends StatelessWidget {
  const _EstadoChip(this.estado);
  final String estado;

  @override
  Widget build(BuildContext context) => Chip(
    label: Text(estado.replaceAll('_', ' ')),
    visualDensity: VisualDensity.compact,
  );
}

class _ParteChip extends StatelessWidget {
  const _ParteChip({required this.parte});
  final DgtParteResumen parte;

  @override
  Widget build(BuildContext context) {
    final complete = parte.estado == 'completado';
    return Chip(
      avatar: Icon(
        complete ? Icons.check_circle : Icons.schedule,
        size: 18,
        color: complete ? Colors.green : null,
      ),
      label: Text(
        '${parte.rol == 'vendedor' ? 'Vendedor' : 'Comprador'}: '
        '${parte.estado.replaceAll('_', ' ')}',
      ),
    );
  }
}

class _EnlaceCard extends StatelessWidget {
  const _EnlaceCard({
    required this.expediente,
    required this.enlace,
    required this.onWhatsApp,
  });

  final DgtExpediente expediente;
  final DgtEnlace enlace;
  final VoidCallback onWhatsApp;

  @override
  Widget build(BuildContext context) {
    final label = enlace.rol == 'vendedor' ? 'Vendedor' : 'Comprador';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 4),
            SelectableText(enlace.url, maxLines: 2),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                FilledButton.icon(
                  key: Key('dgt-whatsapp-${enlace.rol}'),
                  onPressed: onWhatsApp,
                  icon: const Icon(Icons.chat_outlined),
                  label: const Text('WhatsApp'),
                ),
                TextButton.icon(
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: enlace.url));
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('Enlace de $label copiado.')),
                      );
                    }
                  },
                  icon: const Icon(Icons.copy),
                  label: const Text('Copiar'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _NuevoDgtData {
  const _NuevoDgtData({
    required this.titulo,
    required this.vendedorNombre,
    required this.vendedorTelefono,
    required this.compradorNombre,
    required this.compradorTelefono,
  });

  final String titulo;
  final String vendedorNombre;
  final String vendedorTelefono;
  final String compradorNombre;
  final String compradorTelefono;
}

class _NuevoDgtDialog extends StatefulWidget {
  const _NuevoDgtDialog();

  @override
  State<_NuevoDgtDialog> createState() => _NuevoDgtDialogState();
}

class _NuevoDgtDialogState extends State<_NuevoDgtDialog> {
  final _formKey = GlobalKey<FormState>();
  final _titulo = TextEditingController();
  final _vendedorNombre = TextEditingController();
  final _vendedorTelefono = TextEditingController();
  final _compradorNombre = TextEditingController();
  final _compradorTelefono = TextEditingController();

  @override
  void dispose() {
    _titulo.dispose();
    _vendedorNombre.dispose();
    _vendedorTelefono.dispose();
    _compradorNombre.dispose();
    _compradorTelefono.dispose();
    super.dispose();
  }

  String? _validarTelefono(String? value) {
    final digits = (value ?? '').replaceAll(RegExp(r'\D'), '');
    if (digits.length < 9 || digits.length > 15) {
      return 'Indica un teléfono válido para enviar el enlace.';
    }
    return null;
  }

  void _guardar() {
    if (!_formKey.currentState!.validate()) return;
    Navigator.pop(
      context,
      _NuevoDgtData(
        titulo: _titulo.text,
        vendedorNombre: _vendedorNombre.text,
        vendedorTelefono: _vendedorTelefono.text,
        compradorNombre: _compradorNombre.text,
        compradorTelefono: _compradorTelefono.text,
      ),
    );
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Nuevo expediente DGT'),
    content: SizedBox(
      width: 520,
      child: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                key: const Key('dgt-titulo'),
                controller: _titulo,
                decoration: const InputDecoration(
                  labelText: 'Título (opcional)',
                  hintText: 'Cambio de titularidad',
                ),
              ),
              const SizedBox(height: 16),
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Vendedor',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ),
              TextFormField(
                controller: _vendedorNombre,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(labelText: 'Nombre'),
              ),
              TextFormField(
                key: const Key('dgt-vendedor-telefono'),
                controller: _vendedorTelefono,
                keyboardType: TextInputType.phone,
                validator: _validarTelefono,
                decoration: const InputDecoration(labelText: 'Teléfono *'),
              ),
              const SizedBox(height: 16),
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Comprador',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ),
              TextFormField(
                controller: _compradorNombre,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(labelText: 'Nombre'),
              ),
              TextFormField(
                key: const Key('dgt-comprador-telefono'),
                controller: _compradorTelefono,
                keyboardType: TextInputType.phone,
                validator: _validarTelefono,
                decoration: const InputDecoration(labelText: 'Teléfono *'),
                onFieldSubmitted: (_) => _guardar(),
              ),
            ],
          ),
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancelar'),
      ),
      FilledButton(
        key: const Key('dgt-crear-confirmar'),
        onPressed: _guardar,
        child: const Text('Crear y generar enlaces'),
      ),
    ],
  );
}
