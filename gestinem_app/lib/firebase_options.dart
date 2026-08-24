// Fichero generado por FlutterFire CLI.
// PENDIENTE: ejecutar `flutterfire configure --project=gest2a3eco` y
// sustituir este fichero con el generado.
// Los valores necesarios son:
//   apiKey, authDomain, projectId, storageBucket, messagingSenderId, appId
// (todos publicos, se obtienen en Firebase Console > Configuracion del proyecto).
//
// ignore_for_file: lines_longer_than_80_chars

import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) {
      return web;
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      case TargetPlatform.macOS:
        return macos;
      default:
        throw UnsupportedError(
          'DefaultFirebaseOptions no esta configurado para esta plataforma.',
        );
    }
  }

  // Proyecto: gest2a3eco
  // Firebase Console > Ajustes del proyecto > Tus apps > App Web
  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'AIzaSyDQ3EPhHEtySopdHnVW3oDI4ELYo9GDCa4',
    authDomain: 'gest2a3eco.firebaseapp.com',
    projectId: 'gest2a3eco',
    storageBucket: 'gest2a3eco.appspot.com',
    messagingSenderId: '268163516548',
    appId: '1:268163516548:web:3045f4ccec08b0eafddad1',
  );

  // TODO: Obtener de android/app/google-services.json tras ejecutar flutterfire configure.
  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'PENDIENTE_ANDROID_API_KEY',
    appId: 'PENDIENTE_ANDROID_APP_ID',
    messagingSenderId: 'PENDIENTE_SENDER_ID',
    projectId: 'PENDIENTE_PROJECT_ID',
    storageBucket: 'PENDIENTE.appspot.com',
  );

  // TODO: Obtener de ios/Runner/GoogleService-Info.plist tras ejecutar flutterfire configure.
  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'PENDIENTE_IOS_API_KEY',
    appId: 'PENDIENTE_IOS_APP_ID',
    messagingSenderId: 'PENDIENTE_SENDER_ID',
    projectId: 'PENDIENTE_PROJECT_ID',
    storageBucket: 'PENDIENTE.appspot.com',
    iosBundleId: 'es.gestinem.app',
  );

  // TODO: Obtener de macos/Runner/GoogleService-Info.plist tras ejecutar flutterfire configure.
  static const FirebaseOptions macos = FirebaseOptions(
    apiKey: 'PENDIENTE_MACOS_API_KEY',
    appId: 'PENDIENTE_MACOS_APP_ID',
    messagingSenderId: 'PENDIENTE_SENDER_ID',
    projectId: 'PENDIENTE_PROJECT_ID',
    storageBucket: 'PENDIENTE.appspot.com',
    iosBundleId: 'es.gestinem.app',
  );
}
