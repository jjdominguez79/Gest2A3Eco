# Sistema de actualizaciones automaticas

**Estado:** activo.

**Ultima revision contra el codigo:** 2026-08-15.

Este documento describe el contrato tecnico del actualizador. El procedimiento
para publicar una version esta en
[`PUBLICACION_VERSIONES.md`](PUBLICACION_VERSIONES.md).

## Flujo

```text
app_version.py
  -> PyInstaller
  -> Inno Setup
  -> Git tag vX.Y.Z
  -> GitHub Actions crea Release y sube el instalador
  -> workflow actualiza updates/version.json en main

Arranque de la aplicacion
  -> update_checker.py consulta GitHub Raw
  -> compara la version instalada con latest/minimum
  -> ofrece o exige la actualizacion
```

Si no hay conexion o no se puede leer el manifiesto, la aplicacion registra el
problema y continua. Una actualizacion obligatoria bloquea el uso hasta instalar
una version admitida; una opcional puede posponerse.

## Fuentes de version

[`../app_version.py`](../app_version.py) contiene:

```python
APP_VERSION = "X.Y.Z"
APP_RELEASE_DATE = "YYYY-MM-DD"
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/jjdominguez79/Gest2A3Eco/main/updates/version.json"
```

`get_version_label()` genera la etiqueta mostrada por la interfaz. No consulta
Internet: usa exclusivamente la version y fecha empaquetadas.

[`../setup.iss`](../setup.iss) debe contener la misma `MyAppVersion`. El script
de publicacion y `release_utils.py` validan la coherencia entre:

- `app_version.py`;
- `setup.iss`;
- `updates/release_metadata.json`;
- tag `vX.Y.Z`.

## Manifiesto remoto

[`../updates/version.json`](../updates/version.json) se publica mediante GitHub
Raw y contiene:

```json
{
  "latest_version": "X.Y.Z",
  "minimum_required_version": "A.B.C",
  "download_url": "https://github.com/jjdominguez79/Gest2A3Eco/releases/download/vX.Y.Z/Setup_Gest2A3Eco_X.Y.Z.exe",
  "changelog": "Resumen visible para el usuario.",
  "force_update": false
}
```

| Campo | Funcion |
|---|---|
| `latest_version` | Version mas reciente publicada |
| `minimum_required_version` | Version minima que puede continuar |
| `download_url` | Asset exacto de la GitHub Release |
| `changelog` | Novedades mostradas al usuario |
| `force_update` | Fuerza el bloqueo para la nueva version |

Cuando `force_update` es `false`, el workflow conserva el minimo anterior. Si
es `true`, establece la version publicada como nuevo minimo requerido.

## Construccion

El workflow `.github/workflows/publicar-version.yml` usa Windows y Python
3.14.2, instala las dependencias, compila con PyInstaller e instala Inno Setup
6. Los artefactos esperados son:

```text
dist\Gest2A3Eco\Gest2A3Eco.exe
dist_installer\Setup_Gest2A3Eco_X.Y.Z.exe
```

El instalador es un asset de GitHub Release. No se incorpora al historial de
`main`.

Antes de actualizar `version.json`, el workflow comprueba que el asset publicado
responde. Despues cambia a `main`, genera el manifiesto con `release_utils.py` y
hace un commit limitado a ese archivo.

## Comportamiento del cliente

`update_checker.py`:

- compara versiones con semantica `MAJOR.MINOR.PATCH`;
- valida el manifiesto antes de mostrar una actualizacion;
- descarga el instalador a una ubicacion temporal;
- lanza el instalador y permite cerrar la aplicacion de forma controlada;
- distingue actualizacion opcional de version minima obligatoria;
- no usa `updates/release_metadata.json`, que solo participa en publicacion.

## Validacion

```powershell
$env:PYTHONPATH = "."
python -m pytest tests/test_release_utils.py tests/test_version_label_1_7_1.py -q
python -m release_utils validate-release-state `
  --tag vX.Y.Z `
  --repo jjdominguez79/Gest2A3Eco `
  --app-version-file app_version.py `
  --setup-file setup.iss `
  --metadata-file updates/release_metadata.json
```

No deben copiarse numeros de version fijos en esta guia. La fuente de verdad
para una publicacion concreta son los cuatro archivos/valores validados por
`release_utils.py`.
