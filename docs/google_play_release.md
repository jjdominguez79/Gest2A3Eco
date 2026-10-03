# Publicar Gestinem en Google Play

La guía general de versiones está en
[`flutter_production_build.md`](flutter_production_build.md). Este documento
resume únicamente los pasos propios de Google Play.

## Identidad y formato

- Nombre: Gestinem Chat.
- Identificador inmutable: `es.gestinem.app`.
- Formato de entrega: Android App Bundle (`.aab`).
- La versión y el `versionCode` proceden exclusivamente de
  `gestinem_app/pubspec.yaml`.

No cambies el identificador después de crear la aplicación en Play Console.
Cada entrega debe aumentar el número situado después de `+` en `pubspec.yaml`.

## Firma

El equipo de publicación debe conservar fuera del repositorio:

- el `.jks` privado de carga;
- `android/key.properties` con sus cuatro propiedades completas;
- copias de seguridad independientes de la clave.

No subas el `.jks`, sus contraseñas ni `key.properties` a Git. El build release
falla deliberadamente si falta la firma.

## Generar el AAB

Desde `gestinem_app`, con Bash o Warp:

```bash
bash tool/build_production.sh android
```

Con PowerShell:

```powershell
.\tool\build_production.ps1 android
```

Ambos comandos ejecutan dependencias, análisis, pruebas, firma y compilación.
El resultado validado queda en:

```text
build/app/outputs/bundle/release/app-release.aab
```

Sube ese fichero a Google Play Console. El APK generado mediante el comando
`apk` sirve para instalación manual, no para Play Store.

## Subida automatizada

El script puede generar el AAB y subirlo mediante Fastlane, sin modificar la
ficha, las capturas ni otros metadatos de Google Play. Sin opciones de subida,
el comportamiento sigue siendo únicamente generar el fichero local.

La configuración inicial requiere:

1. activar Google Play Developer API en el proyecto de Google Cloud vinculado;
2. crear una cuenta de servicio;
3. autorizarla para esta aplicación en Usuarios y permisos de Play Console;
4. instalar Fastlane;
5. guardar la credencial fuera del repositorio y definir su ruta:

```powershell
$env:GOOGLE_PLAY_CREDENTIALS_PATH = 'C:\credenciales\gestinem-play.json'
```

Para subir una entrega a producción dejándola pendiente de envío a revisión:

```powershell
.\tool\build_production.ps1 android -UploadPlay -PlayTrack production
```

Para subirla a producción y enviarla directamente a revisión:

```powershell
.\tool\build_production.ps1 android -UploadPlay -PlayTrack production -SubmitPlayReview
```

Elige uno de los dos comandos para cada `versionCode`: Google Play no permite
subir dos veces la misma compilación. `-SubmitPlayReview` requiere
`-UploadPlay`. Las pistas admitidas son `internal`, `alpha`, `beta` y
`production`; la predeterminada es `internal` para reducir el riesgo de una
publicación accidental.

Equivalente Bash:

```bash
GOOGLE_PLAY_CREDENTIALS_PATH=/credenciales/gestinem-play.json \
PLAY_UPLOAD=1 PLAY_TRACK=production \
bash tool/build_production.sh android

GOOGLE_PLAY_CREDENTIALS_PATH=/credenciales/gestinem-play.json \
PLAY_UPLOAD=1 PLAY_TRACK=production PLAY_SUBMIT_REVIEW=1 \
bash tool/build_production.sh android
```

La credencial nunca debe guardarse en el repositorio. Para CI es preferible una
credencial temporal obtenida mediante Workload Identity Federation.

## Actualizaciones dentro de la aplicación

Desde la compilación 40, el cliente Android consulta directamente a Google
Play al abrirse y al volver al primer plano:

- una actualización normal usa el flujo flexible de Google Play;
- una actualización obligatoria usa el flujo inmediato y bloqueante;
- si Play Core no puede iniciar el flujo, se ofrece la ficha pública como
  alternativa.

No hay que actualizar `MESSAGING_ANDROID_LATEST_APP_VERSION` ni
`MESSAGING_ANDROID_LATEST_APP_BUILD` en cada publicación. Google Play determina
la versión disponible a partir del `versionCode` publicado.

El backend se conserva únicamente como interruptor de emergencia. Mantén:

```text
MESSAGING_ANDROID_UPDATE_ENABLED=true
MESSAGING_ANDROID_MINIMUM_APP_BUILD=1
MESSAGING_ANDROID_STORE_URL=https://play.google.com/store/apps/details?id=es.gestinem.app
```

Solo aumenta `MESSAGING_ANDROID_MINIMUM_APP_BUILD` cuando una versión antigua
deba dejar de funcionar. Hazlo después de que la compilación mínima esté
disponible al 100 % en producción; de lo contrario podrías bloquear a usuarios
que todavía no pueden recibirla.

### Migración inicial a la compilación 40

Las compilaciones 39 e inferiores aún usan el aviso antiguo. Para conducirlas
a la primera versión con Play In-App Updates, configura una última vez:

```text
MESSAGING_ANDROID_UPDATE_ENABLED=true
MESSAGING_ANDROID_LATEST_APP_VERSION=0.1.25
MESSAGING_ANDROID_LATEST_APP_BUILD=40
MESSAGING_ANDROID_MINIMUM_APP_BUILD=40
```

Activa esos valores solo cuando la compilación 40 ya esté publicada al 100 %.
Las versiones 40 y posteriores no dependerán de `LATEST_APP_VERSION` ni de
`LATEST_APP_BUILD` para descubrir nuevas actualizaciones.

El flujo nativo únicamente puede probarse en un dispositivo con la aplicación
instalada desde Google Play; no funciona con una instalación local por APK.

## Comprobaciones en Play Console

- El `versionCode` debe ser superior al de todas las entregas anteriores.
- El país, la pista y el porcentaje de lanzamiento deben ser los deseados.
- La ficha, privacidad, seguridad de los datos, audiencia y acceso de revisión
  deben seguir vigentes.
- La política pública es `https://www.gestinem.es/app/privacidad/`.
- La eliminación de cuenta es
  `https://www.gestinem.es/app/eliminar-cuenta/`.
- Comprueba el `targetSdkVersion` efectivo que exija Google Play en la fecha de
  la publicación.

## Referencias oficiales

- Firma y Play App Signing:
  https://developer.android.com/studio/publish/app-signing
- Subida de Android App Bundles:
  https://support.google.com/googleplay/android-developer/answer/9859152?hl=es
- Requisitos de API de destino:
  https://support.google.com/googleplay/android-developer/answer/11926878?hl=es
- Seguridad de los datos:
  https://support.google.com/googleplay/android-developer/answer/10787469?hl=es
