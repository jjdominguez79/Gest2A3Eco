import 'dart:io';

import 'package:flutter_native_contact_picker/flutter_native_contact_picker.dart';

import '../domain/message.dart';

bool get selectorContactoNativoDisponible => Platform.isAndroid || Platform.isIOS;

Future<SharedContact?> seleccionarContactoNativo() async {
  final contacto = await FlutterNativeContactPicker().selectPhoneNumber();
  if (contacto == null) return null;

  final telefono =
      contacto.selectedPhoneNumber?.trim() ??
      contacto.phoneNumbers?.firstOrNull?.trim() ??
      '';
  final nombreSeleccionado = contacto.fullName?.trim() ?? '';
  final nombre = nombreSeleccionado.isEmpty ? telefono : nombreSeleccionado;
  if (nombre.isEmpty || telefono.isEmpty) return null;

  return SharedContact(name: nombre, phone: telefono);
}
