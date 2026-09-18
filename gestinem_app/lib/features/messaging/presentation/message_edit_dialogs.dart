import 'package:flutter/material.dart';

import '../../../core/api/api_client.dart';
import '../domain/message.dart';

Future<bool> editarMensaje(
  BuildContext context,
  Message mensaje,
  Future<void> Function(String texto) guardar,
) async {
  return await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _DialogoEdicion(mensaje: mensaje, guardar: guardar),
      ) ??
      false;
}

class _DialogoEdicion extends StatefulWidget {
  const _DialogoEdicion({required this.mensaje, required this.guardar});
  final Message mensaje;
  final Future<void> Function(String texto) guardar;

  @override
  State<_DialogoEdicion> createState() => _DialogoEdicionState();
}

class _DialogoEdicionState extends State<_DialogoEdicion> {
  late final _texto = TextEditingController(text: widget.mensaje.body);
  bool _guardando = false;
  String? _error;

  @override
  void dispose() {
    _texto.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    final texto = _texto.text.trim();
    if (texto.isEmpty) {
      setState(() => _error = 'El mensaje no puede estar vacio');
      return;
    }
    if (texto == widget.mensaje.body) {
      Navigator.pop(context, false);
      return;
    }
    setState(() {
      _guardando = true;
      _error = null;
    });
    try {
      await widget.guardar(texto);
      if (mounted) {
        Navigator.pop(context, true);
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = apiErrorMessage(error);
          _guardando = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_guardando,
    child: AlertDialog(
      title: const Text('Editar mensaje'),
      content: SizedBox(
        width: 480,
        child: TextField(
          key: const Key('edit-message-body'),
          controller: _texto,
          autofocus: true,
          enabled: !_guardando,
          minLines: 3,
          maxLines: 8,
          maxLength: 20000,
          decoration: InputDecoration(labelText: 'Mensaje', errorText: _error),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _guardando ? null : () => Navigator.pop(context, false),
          child: const Text('Cancelar'),
        ),
        FilledButton(
          onPressed: _guardando ? null : _guardar,
          child: Text(_guardando ? 'Guardando...' : 'Guardar'),
        ),
      ],
    ),
  );
}

Future<void> verHistorialMensaje(
  BuildContext context,
  Future<List<MessageVersion>> Function() cargar,
) {
  return showDialog<void>(
    context: context,
    builder: (_) => _DialogoHistorial(cargar: cargar),
  );
}

class _DialogoHistorial extends StatefulWidget {
  const _DialogoHistorial({required this.cargar});
  final Future<List<MessageVersion>> Function() cargar;

  @override
  State<_DialogoHistorial> createState() => _DialogoHistorialState();
}

class _DialogoHistorialState extends State<_DialogoHistorial> {
  late final _versiones = widget.cargar();

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Versiones anteriores'),
    content: SizedBox(
      width: 480,
      height: 360,
      child: FutureBuilder<List<MessageVersion>>(
        future: _versiones,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return Text(apiErrorMessage(snapshot.error!));
          }
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final datos = snapshot.data!;
          if (datos.isEmpty) {
            return const Text('No hay versiones anteriores.');
          }
          return ListView.separated(
            itemCount: datos.length,
            separatorBuilder: (_, _) => const Divider(),
            itemBuilder: (context, index) => ListTile(
              title: Text(index == 0 ? 'Original' : 'Version ${index + 1}'),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${_fechaVersion(datos[index].createdAt)} - ${_fechaVersion(datos[index].replacedAt)}',
                  ),
                  const SizedBox(height: 8),
                  SelectableText(datos[index].body),
                ],
              ),
            ),
          );
        },
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cerrar'),
      ),
    ],
  );
}

String _fechaVersion(DateTime fecha) {
  String dos(int valor) => valor.toString().padLeft(2, '0');
  return '${dos(fecha.day)}/${dos(fecha.month)}/${fecha.year} '
      '${dos(fecha.hour)}:${dos(fecha.minute)}:${dos(fecha.second)}';
}
