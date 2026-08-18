import 'external_auth_handoff_stub.dart'
    if (dart.library.io) 'external_auth_handoff_io.dart'
    as implementation;

Future<void> finishExternalAuthHandoff() =>
    implementation.finishExternalAuthHandoff();
