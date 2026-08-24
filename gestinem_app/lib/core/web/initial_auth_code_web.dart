import 'package:web/web.dart' as web;

String? leerCodigoStaffInicial() {
  final uri = Uri.tryParse(web.window.location.href);
  if (uri == null) return null;

  final directo = uri.queryParameters['code'];
  if (directo != null && directo.isNotEmpty) return directo;

  final inicioQuery = uri.fragment.indexOf('?');
  if (inicioQuery < 0) return null;
  return Uri.tryParse(
    uri.fragment.substring(inicioQuery),
  )?.queryParameters['code'];
}
