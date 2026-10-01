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
