# Publicacion de Gestinem en Google Play

Estado de preparacion: compilacion Android configurada, pero la primera version
publica no debe enviarse hasta completar los puntos marcados como pendientes.

## Identidad de la aplicacion

- Nombre: `Gestinem`
- Identificador inmutable: `es.gestinem.app`
- Version preparada: `0.1.1` (`versionCode` 8)
- Backend de produccion actual:
  `https://gest2a3eco-production.up.railway.app`
- Formato de entrega: Android App Bundle (`.aab`)

El identificador no se debe cambiar despues de crear la aplicacion en Play
Console. Cada entrega posterior debe aumentar el `versionCode` de `pubspec.yaml`.

## 1. Clave de carga (pendiente)

Crear una clave privada de carga y conservar al menos dos copias de seguridad
fuera del repositorio. No subir el `.jks`, sus contrasenas ni
`android/key.properties` a Git.

```powershell
keytool -genkeypair -v `
  -keystore C:\ruta\privada\gestinem-upload.jks `
  -keyalg RSA -keysize 2048 -validity 10000 -alias gestinem

Copy-Item android\key.properties.example android\key.properties
```

Completar las cuatro propiedades de `android/key.properties`. La compilacion
`release` falla expresamente si falta esta configuracion, para impedir la
entrega accidental de un paquete sin firma. Al crear la aplicacion en Play
Console, activar **Play App Signing** y usar este certificado como clave de
carga.

## 2. Generar el App Bundle

```powershell
Set-Location gestinem_app
flutter clean
flutter pub get
flutter analyze
flutter test
flutter build appbundle --release `
  --dart-define=API_BASE_URL=https://gest2a3eco-production.up.railway.app `
  --dart-define=ENVIRONMENT=production
```

Resultado esperado:
`build/app/outputs/bundle/release/app-release.aab`.

Antes del envio definitivo conviene activar `https://app.gestinem.es` y generar
el bundle con ese dominio para no vincular la primera version publica a la URL
temporal de Railway.

## 3. Requisitos de Play Console (pendientes)

- Crear la ficha con el paquete `es.gestinem.app` y activar Play App Signing.
- Publicar una politica de privacidad en una URL publica de `gestinem.es`.
- Completar Seguridad de los datos de acuerdo con el funcionamiento real:
  identidad de usuario, mensajes, archivos adjuntos, avatar e identificador de
  notificaciones; trafico cifrado; uso de Firebase Cloud Messaging y del
  alojamiento del backend.
- Publicar una pagina web para solicitar la eliminacion de la cuenta y enlazarla
  desde la aplicacion. Hay que definir antes que datos se borran y cuales se
  conservan por obligaciones legales o de seguridad.
- Indicar en **Acceso a la aplicacion** unas credenciales de cliente de revision
  que permitan a Google entrar sin depender de una invitacion caducada.
- Completar clasificacion de contenido, audiencia, declaracion de anuncios y
  datos de contacto.
- Preparar icono de ficha de 512 x 512, grafico de funciones de 1024 x 500 y
  capturas de telefono sin datos reales de clientes.
- Ejecutar primero una prueba interna y despues una prueba cerrada antes de
  solicitar produccion.

## 4. Compatibilidad Android

En cada publicacion se debe comprobar el `targetSdkVersion` efectivo del bundle.
A partir del 31 de agosto de 2026, las aplicaciones nuevas y sus actualizaciones
para telefono deben orientarse a Android 16 (API 36) o posterior.

## Referencias oficiales

- Firma y Play App Signing:
  https://developer.android.com/studio/publish/app-signing
- Subida de Android App Bundles:
  https://developer.android.com/studio/publish/upload-bundle
- API de destino:
  https://support.google.com/googleplay/android-developer/answer/11926878?hl=es
- Seguridad de los datos:
  https://support.google.com/googleplay/android-developer/answer/10787469?hl=es
- Eliminacion de cuentas:
  https://support.google.com/googleplay/android-developer/answer/13327111?hl=es
