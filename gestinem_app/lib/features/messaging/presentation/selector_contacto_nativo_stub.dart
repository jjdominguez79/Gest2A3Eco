import '../domain/message.dart';

bool get selectorContactoNativoDisponible => false;

Future<SharedContact?> seleccionarContactoNativo() {
  throw UnsupportedError('El selector nativo no esta disponible');
}
