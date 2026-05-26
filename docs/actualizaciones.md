# Sistema de actualizaciones automáticas - Gest2A3Eco

## Resumen del flujo

```text
Nueva versión lista
       |
       v
1. Mantener APP_VERSION en app_version.py
2. Compilar .exe con PyInstaller
3. Generar instalador .exe con Inno Setup
4. Crear tag vX.Y.Z
5. Publicar release en GitHub
6. Subir el instalador como asset del release
7. Actualizar updates/version.json
       |
       v
Al arrancar la app:
  update_checker.py descarga version.json desde GitHub Raw
  Si hay actualización obligatoria -> bloquea y ofrece descargar
  Si hay actualización opcional    -> ofrece descargar, permite omitir
  Si no hay conexión               -> continúa sin interrupciones
```

## 1. Versión actual de la aplicación

La versión actual se mantiene en [app_version.py](/C:/Users/GestinemFiscal/Gest2A3Eco/app_version.py:1):

```python
APP_VERSION = "1.1.0"
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/jjdominguez79/Gest2A3Eco/main/updates/version.json"
```

Usar siempre formato semver: `MAJOR.MINOR.PATCH`.

## 2. Dónde se publica `version.json`

El archivo [updates/version.json](/C:/Users/GestinemFiscal/Gest2A3Eco/updates/version.json:1) vive en el repositorio y debe quedar accesible mediante GitHub Raw:

```text
https://raw.githubusercontent.com/jjdominguez79/Gest2A3Eco/main/updates/version.json
```

Ese es el endpoint que consulta la aplicación al iniciarse.

## 3. Generar el ejecutable con PyInstaller

Requisitos previos:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

Compilación:

```bash
pyinstaller Gest2A3Eco.spec
```

El ejecutable principal queda en `dist\Gest2A3Eco\Gest2A3Eco.exe`.

## 4. Generar el instalador con Inno Setup

La versión de [setup.iss](/C:/Users/GestinemFiscal/Gest2A3Eco/setup.iss:17) debe coincidir con `APP_VERSION`:

```iss
#define MyAppVersion   "1.1.0"
```

Compilación:

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup.iss
```

El instalador esperado para esta versión es:

```text
dist_installer\Setup_Gest2A3Eco_1.1.0.exe
```

## 5. Publicar releases en GitHub

Cada versión distribuible debe publicarse como GitHub Release.

Reglas obligatorias:

- Cada release debe tener un tag con formato `vX.Y.Z`, por ejemplo `v1.1.0`.
- El instalador debe subirse como asset del release, no al repositorio normal.
- No deben subirse instaladores `.exe` al árbol del repositorio ni a commits de `main`.
- El nombre del instalador debe coincidir exactamente con el indicado en `download_url`.

Para la versión `1.1.0`, la URL de descarga queda así:

```text
https://github.com/jjdominguez79/Gest2A3Eco/releases/download/v1.1.0/Setup_Gest2A3Eco_1.1.0.exe
```

## 6. Estructura de `version.json`

Contenido inicial de [updates/version.json](/C:/Users/GestinemFiscal/Gest2A3Eco/updates/version.json:1):

```json
{
  "latest_version": "1.1.0",
  "minimum_required_version": "1.1.0",
  "download_url": "https://github.com/jjdominguez79/Gest2A3Eco/releases/download/v1.1.0/Setup_Gest2A3Eco_1.1.0.exe",
  "changelog": "Primera versión con sistema de actualización automática.",
  "force_update": false
}
```

Campos:

| Campo | Tipo | Descripción |
|---|---|---|
| `latest_version` | string | Versión más reciente disponible |
| `minimum_required_version` | string | Versión mínima permitida |
| `download_url` | string | URL exacta del asset del release |
| `changelog` | string | Novedades visibles para el usuario |
| `force_update` | boolean | Si es `true`, obliga a actualizar |

## 7. Checklist de nueva versión

```text
[ ] 1. Desarrollar y probar los cambios
[ ] 2. Actualizar APP_VERSION en app_version.py
[ ] 3. Actualizar #define MyAppVersion en setup.iss
[ ] 4. Generar el tag vX.Y.Z
[ ] 5. Ejecutar pyinstaller Gest2A3Eco.spec
[ ] 6. Probar dist\Gest2A3Eco\Gest2A3Eco.exe
[ ] 7. Compilar setup.iss con ISCC
[ ] 8. Crear GitHub Release para el tag vX.Y.Z
[ ] 9. Subir Setup_Gest2A3Eco_X.Y.Z.exe como asset del release
[ ] 10. Actualizar updates/version.json
[ ] 11. Verificar GitHub Raw y la URL del asset
[ ] 12. Probar la actualización desde una versión anterior
```

## 8. Estructura de archivos relevantes

```text
Gest2A3Eco/
|-- app_version.py
|-- update_checker.py
|-- setup.iss
|-- Gest2A3Eco.spec
|-- updates/
|   `-- version.json
`-- docs/
    `-- actualizaciones.md
```

## 9. Notas operativas

- `update_checker.py` no necesita cambios para este flujo mientras `version.json` siga teniendo la misma estructura.
- Si `version.json` no es accesible, la aplicación continúa iniciándose con normalidad.
- `requests` consulta tanto `version.json` como el instalador remoto.
