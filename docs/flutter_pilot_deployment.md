# Despliegue piloto de Gestinem Flutter — HISTÓRICO

> Este documento se conserva únicamente como referencia del piloto inicial. No debe usarse para generar versiones actuales. Para producción consulta `docs/flutter_production_build.md` y `gestinem_app/README.md`.

## Configuración que nació durante el piloto

El backend adoptado y todavía vigente es:

`https://gest2a3eco-production.up.railway.app`

El frontend web se publica en Firebase Hosting y usa `https://app.gestinem.es`.

En Railway se configuró Firebase Admin mediante `MESSAGING_FIREBASE_CREDENTIALS_JSON`; esas credenciales nunca deben guardarse en Git ni incluirse en Flutter. El fichero Android `google-services.json` permanece local en `gestinem_app/android/app/`.

La configuración de dominios del piloto estableció:

```text
DGT_PUBLIC_BASE_URL=https://gest2a3eco-production.up.railway.app
MESSAGING_PUBLIC_BASE_URL=https://gest2a3eco-production.up.railway.app
MESSAGING_APP_WEB_REDIRECT_URI=https://app.gestinem.es/auth/callback
```

Y en Microsoft Entra:

```text
https://gest2a3eco-production.up.railway.app/api/v1/messaging/staff-auth/callback
```

Cuando exista un dominio API independiente como `api.gestinem.es`, la migración debe coordinar backend, redirecciones Microsoft, CORS y todos los clientes Flutter.

## Procedimiento antiguo retirado

Durante el piloto se generaban APK `debug` para dispositivos concretos. Ese procedimiento ya no es válido para distribución.

La producción Android actual usa un **AAB release firmado** y se genera mediante:

```bash
cd gestinem_app
bash tool/build_production.sh android
```

O en PowerShell:

```powershell
cd gestinem_app
.\tool\build_production.ps1 android
```

No añadas nuevos procedimientos de build a este documento. Mantén la documentación operativa en `docs/flutter_production_build.md`.
