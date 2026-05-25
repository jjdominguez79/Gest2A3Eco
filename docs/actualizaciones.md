# Sistema de actualizaciones automáticas — Gest2A3Eco

## Resumen del flujo

```
Nueva versión lista
       │
       ▼
1. Actualizar APP_VERSION en app_version.py
2. Compilar .exe con PyInstaller
3. Generar instalador .exe con Inno Setup
4. Subir el instalador al servidor web
5. Actualizar version.json en el servidor
       │
       ▼
Al arrancar la app (usuario final):
  update_checker.py descarga version.json
  Si hay actualización obligatoria → bloquea y ofrece descargar
  Si hay actualización opcional    → ofrece descargar, permite omitir
  Si no hay conexión               → continúa sin interrupciones
```

---

## 1. Cambiar la versión de la aplicación

Editar el archivo `app_version.py` en la raíz del proyecto:

```python
APP_VERSION = "1.2.0"   # ← nueva versión
UPDATE_CHECK_URL = "https://actualizaciones.gestinem.es/gest2a3eco/version.json"
```

Usar siempre formato **semver** (`MAJOR.MINOR.PATCH`). Ejemplos válidos:
`1.0.0`, `1.0.1`, `1.1.0`, `2.0.0`.

---

## 2. Configurar la URL de actualizaciones

La constante `UPDATE_CHECK_URL` en `app_version.py` apunta al `version.json` público.
Cambiarla al servidor real antes de distribuir la primera versión:

```python
UPDATE_CHECK_URL = "https://mi-servidor.com/gest2a3eco/version.json"
```

El servidor debe servir el archivo con `Content-Type: application/json`
y ser accesible por HTTPS desde la red del cliente.

---

## 3. Generar el ejecutable con PyInstaller

**Requisitos previos:**

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

**Compilar:**

```bash
pyinstaller Gest2A3Eco.spec
```

Los archivos resultantes quedan en `dist\Gest2A3Eco\`.
El ejecutable principal es `dist\Gest2A3Eco\Gest2A3Eco.exe`.

**Verificar que funciona antes de empaquetar:**

```bash
dist\Gest2A3Eco\Gest2A3Eco.exe
```

---

## 4. Generar el instalador con Inno Setup

**Requisitos previos:**

- Inno Setup 6.x instalado: https://jrsoftware.org/isinfo.php
- El paso 3 (PyInstaller) completado con éxito.

**Actualizar la versión en `setup.iss`** (debe coincidir con `app_version.py`):

```iss
#define MyAppVersion   "1.2.0"
```

**Compilar el instalador:**

```bash
# Opción A: línea de comandos
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup.iss

# Opción B: IDE de Inno Setup
# Abrir setup.iss → menú Build → Compile (F9)
```

El instalador resultante se guarda en:

```
dist_installer\Setup_Gest2A3Eco_1.2.0.exe
```

**Crear la carpeta si no existe:**

```bash
mkdir dist_installer
```

---

## 5. Subir el instalador al servidor

Copiar el instalador al servidor web accesible públicamente:

```
https://actualizaciones.gestinem.es/gest2a3eco/Setup_Gest2A3Eco_1.2.0.exe
```

La URL exacta debe coincidir con el campo `download_url` del `version.json`.

---

## 6. Actualizar el archivo `version.json` remoto

Este es el archivo que consulta la aplicación al arrancar.
Debe estar publicado en la URL definida en `UPDATE_CHECK_URL`.

**Estructura del archivo:**

```json
{
  "latest_version": "1.2.0",
  "minimum_required_version": "1.0.0",
  "download_url": "https://actualizaciones.gestinem.es/gest2a3eco/Setup_Gest2A3Eco_1.2.0.exe",
  "changelog": "- Corrección de error en normalización de NIF\n- Mejoras en el dashboard\n- Nueva gestión de terceros",
  "force_update": false
}
```

**Campos:**

| Campo | Tipo | Descripción |
|---|---|---|
| `latest_version` | string | Versión más reciente disponible |
| `minimum_required_version` | string | Versión mínima permitida (inferior → bloqueo) |
| `download_url` | string | URL directa al instalador .exe |
| `changelog` | string | Texto libre con las novedades (soporta `\n`) |
| `force_update` | boolean | `true` fuerza actualización aunque cumpla mínimo |

---

## 7. Forzar una actualización obligatoria

Hay **dos mecanismos** para obligar a actualizar:

### Mecanismo A — `minimum_required_version`

Si la versión instalada en el cliente es **inferior** a `minimum_required_version`,
la aplicación **bloquea el acceso** y solo ofrece "Descargar e instalar" o "Salir".

Ejemplo: forzar que todos los clientes con versión < 1.2.0 actualicen:

```json
{
  "latest_version": "1.2.0",
  "minimum_required_version": "1.2.0",
  "download_url": "...",
  "changelog": "Actualización de seguridad obligatoria.",
  "force_update": false
}
```

### Mecanismo B — `force_update: true`

Si `force_update` es `true`, **todos los clientes** con cualquier versión anterior
a `latest_version` son bloqueados, independientemente de `minimum_required_version`.

```json
{
  "latest_version": "1.2.0",
  "minimum_required_version": "1.0.0",
  "download_url": "...",
  "changelog": "Cambio de base de datos obligatorio.",
  "force_update": true
}
```

**Cuándo usar cada uno:**

- `minimum_required_version`: cuando solo algunas versiones antiguas son incompatibles.
- `force_update: true`: cuando TODOS deben actualizar sin excepción (migración de BD, cambio de protocolo, etc.).

---

## 8. Publicar una actualización opcional

Si `force_update` es `false` y la versión instalada es mayor o igual que
`minimum_required_version`, la actualización es **opcional**:
el usuario puede pulsar "Ahora no" y continuar usando la aplicación.

```json
{
  "latest_version": "1.2.0",
  "minimum_required_version": "1.0.0",
  "download_url": "...",
  "changelog": "Mejoras de rendimiento y correcciones menores.",
  "force_update": false
}
```

---

## 9. Flujo completo paso a paso (checklist de nueva versión)

```
[ ] 1. Desarrollar y probar los cambios
[ ] 2. Actualizar APP_VERSION en app_version.py
[ ] 3. Actualizar #define MyAppVersion en setup.iss
[ ] 4. Hacer commit y push (git tag vX.Y.Z recomendado)
[ ] 5. pyinstaller Gest2A3Eco.spec
[ ] 6. Probar dist\Gest2A3Eco\Gest2A3Eco.exe manualmente
[ ] 7. ISCC.exe setup.iss
[ ] 8. Subir dist_installer\Setup_Gest2A3Eco_X.Y.Z.exe al servidor
[ ] 9. Actualizar version.json en el servidor
[ ] 10. Verificar que la URL de descarga es accesible públicamente
[ ] 11. Probar el flujo de actualización desde una versión anterior
```

---

## 10. Estructura de archivos relevantes

```
Gest2A3Eco/
├── app_version.py          ← versión actual y URL de comprobación
├── update_checker.py       ← lógica de comprobación y diálogo de actualización
├── main.py                 ← integración del check al inicio de la app
├── setup.iss               ← script de Inno Setup para generar el instalador
├── Gest2A3Eco.spec         ← configuración de PyInstaller
├── requirements.txt        ← dependencias Python (incluye requests, packaging)
└── docs/
    └── actualizaciones.md  ← este documento
```

---

## 11. Dependencias Python necesarias

El sistema de actualizaciones requiere:

```
requests    — consulta HTTP a version.json y descarga del instalador
packaging   — comparación correcta de versiones semánticas (PEP 440)
```

Ambas están incluidas en `requirements.txt`. Para instalarlas manualmente:

```bash
pip install requests packaging
```

PyInstaller las incluye automáticamente en el .exe al compilar con `Gest2A3Eco.spec`.

---

## 12. Comportamiento sin conexión a internet

Si `version.json` no es accesible (sin red, servidor caído, timeout):

- La aplicación **continúa iniciándose con normalidad**.
- Se registra un aviso en el log (`logging.WARNING`).
- No se muestra ningún diálogo al usuario.

El timeout de la comprobación es de **5 segundos** (configurable en `_TIMEOUT_CHECK`
dentro de `update_checker.py`).

---

## 13. Localización del log de actualizaciones

Los mensajes del sistema de actualizaciones se registran con el logger:

```python
logging.getLogger("update_checker")
```

Para verlos, añadir un handler al arrancar la aplicación:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

---

## 14. Datos del usuario preservados durante una actualización

El instalador de Inno Setup **no sobreescribe** la carpeta `plantillas\`:

- `plantillas\gest2a3eco.db` — base de datos SQLite (conservada)
- `plantillas\plantillas.json` — semilla JSON (conservada)
- `plantillas\email_factura.html` — plantilla de email (conservada)
- `config.json` — configuración SMTP y rutas (conservada)
- `config.local.json` — configuración local (conservada)
- `pdfs_emitidas\` — PDFs generados (conservados)

Solo se actualizan los archivos binarios de la aplicación.
