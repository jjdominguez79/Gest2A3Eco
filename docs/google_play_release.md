# Publicacion de Gestinem en Google Play

Estado de publicacion (24 de septiembre de 2026): la version `0.1.18` (33) se
ha enviado a revision de Google Play para un lanzamiento completo en Espana.
Google Play indica que la revision suele completarse en un plazo de 7 dias,
aunque puede tardar mas.

## Identidad de la aplicacion

- Nombre: `Gestinem Chat`
- Identificador inmutable: `es.gestinem.app`
- Version preparada: `0.1.18` (`versionCode` 33)
- Backend de produccion actual:
  `https://gest2a3eco-production.up.railway.app`
- Formato de entrega: Android App Bundle (`.aab`)

El identificador no se debe cambiar despues de crear la aplicacion en Play
Console. Cada entrega posterior debe aumentar el `versionCode` de `pubspec.yaml`.

## 1. Clave de carga

La clave privada de carga ya esta configurada en este equipo. Conservar al
menos dos copias de seguridad fuera del repositorio. No subir el `.jks`, sus
contrasenas ni `android/key.properties` a Git.

```powershell
keytool -genkeypair -v `
  -keystore C:\ruta\privada\gestinem-upload.jks `
  -keyalg RSA -keysize 2048 -validity 10000 -alias gestinem

Copy-Item android\key.properties.example android\key.properties
```

Las cuatro propiedades de `android/key.properties` deben permanecer completas. La compilacion
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

## 3. Requisitos de Play Console

Completado y enviado a revision:

- Ficha en espanol con textos, icono, grafico de funciones y cuatro capturas.
- Seguridad de los datos, audiencia, clasificacion, anuncios, acceso para
  revision, contacto, pagina de eliminacion y prueba interna.
- Politica publica en `https://www.gestinem.es/app/privacidad/` y eliminacion en
  `https://www.gestinem.es/app/eliminar-cuenta/`.
- App Bundle 33 publicado en prueba interna y enviado a produccion con
  `targetSdkVersion` 36.
- URL de privacidad de Play Console corregida de la antigua URL con error 404 a
  `https://www.gestinem.es/app/privacidad/`.
- Declaracion de que la aplicacion no usa el ID de publicidad; el manifiesto final no
  contiene `com.google.android.gms.permission.AD_ID`.
- El manifiesto final ya no contiene
  `READ_MEDIA_IMAGES`, `READ_MEDIA_VIDEO`, `READ_MEDIA_AUDIO` ni
  `READ_EXTERNAL_STORAGE`, porque los adjuntos usan el selector del sistema.
- Seguridad de los datos actualizada para incluir grabaciones de voz como dato
  opcional, recogido para la funcionalidad de la aplicacion y no compartido.
- Produccion limitada a Espana y lanzamiento completo de la version 33 enviado
  a revision junto con la ficha y las declaraciones pendientes.

Completado fuera de Play Console:

- Politica publica de WordPress corregida para indicar que la aplicacion usa
  el microfono solamente cuando el usuario decide grabar una nota de voz, e
  incluir las grabaciones de audio, Railway y la fecha de actualizacion.

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
