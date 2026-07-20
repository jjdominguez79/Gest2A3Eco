# Publicacion de versiones de Gest2A3Eco

## Objetivo

Este flujo permite publicar una nueva version de Gest2A3Eco desde Windows con un unico comando local:

```powershell
.\publicar_version.ps1
```

o bien:

```text
publicar_version.bat
```

El script local prepara la version, hace commit, push y crea el tag `vX.Y.Z`.
GitHub Actions detecta ese tag, compila la aplicacion, genera el instalador, crea la GitHub Release y actualiza `updates/version.json`.

No hace falta:

- instalar GitHub CLI;
- ejecutar `gh auth login`;
- crear la Release a mano;
- subir el instalador manualmente;
- escribir manualmente la URL en `updates/version.json`.

## Primera configuracion

Antes de la primera publicacion:

1. Comprueba que Git funciona:

```powershell
git --version
```

2. Comprueba que tus credenciales Git ya estan configuradas y que puedes hacer push a `main`:

```powershell
git remote -v
git fetch origin
git push --dry-run origin main
```

3. Comprueba que Python esta disponible:

```powershell
python --version
```

4. Revisa en GitHub:

```text
Settings
Actions
General
Workflow permissions
Read and write permissions
```

El workflow necesita permisos de escritura para:

- crear la Release;
- subir el instalador;
- hacer commit de `updates/version.json`.

5. Si `main` tiene proteccion de rama, confirma que `github-actions[bot]` puede hacer push al menos para actualizar `updates/version.json`.

## Flujo final

### Script local

`publicar_version.ps1`:

1. valida que estas en `main`;
2. valida el remoto `origin` contra `jjdominguez79/Gest2A3Eco`;
3. hace `git fetch origin` y `git pull --ff-only origin main`;
4. detecta cambios locales y te pregunta si quieres incluirlos;
5. pide la nueva version `X.Y.Z`;
6. pide el changelog multilinea;
7. pide si la actualizacion es obligatoria;
8. muestra resumen final;
9. solo continua si escribes exactamente `PUBLICAR`;
10. actualiza:
   `app_version.py`
   `setup.iss`
   `updates/release_metadata.json`
11. crea el commit de preparacion;
12. hace push a `main`;
13. crea el tag anotado `vX.Y.Z`;
14. hace push del tag;
15. espera a que GitHub Actions actualice `updates/version.json` en `main`;
16. hace `git pull --ff-only origin main` automaticamente cuando el remoto ya contiene la nueva version.

### GitHub Actions

`.github/workflows/publicar-version.yml`:

1. se ejecuta al subir un tag `v*.*.*`;
2. valida que el tag, `app_version.py`, `setup.iss` y `updates/release_metadata.json` coinciden;
3. instala dependencias Python;
4. compila con PyInstaller;
5. valida `dist\Gest2A3Eco\Gest2A3Eco.exe`;
6. instala Inno Setup 6;
7. genera y valida `dist_installer\Setup_Gest2A3Eco_X.Y.Z.exe`;
8. crea la GitHub Release;
9. verifica que la URL publica del asset responde;
10. cambia a `main`;
11. actualiza `updates/version.json`;
12. hace commit y push solo de `updates/version.json`.

## Publicar una nueva version

1. Termina los cambios de codigo.
2. Ejecuta pruebas locales.
3. Ejecuta:

```powershell
.\publicar_version.ps1
```

o:

```text
publicar_version.bat
```

4. Introduce la version `X.Y.Z`.
5. Escribe el changelog y termina con una linea que contenga solo `FIN`.
6. Indica `S` o `N` si la actualizacion sera obligatoria.
7. Revisa el resumen.
8. Confirma escribiendo exactamente `PUBLICAR`.
9. Abre GitHub Actions y sigue la ejecucion del workflow `Publicar version`.
10. El script intentara sincronizar tu repo local automaticamente cuando el workflow actualice `updates/version.json`.
11. Cuando termine, prueba la actualizacion desde una version anterior.

## Notas sobre actualizaciones opcionales y obligatorias

`force_update` decide si el cliente debe bloquearse.

Para que una actualizacion opcional siga siendo opcional:

- si `force_update` es `true`, el workflow fija `minimum_required_version` a la nueva version;
- si `force_update` es `false`, el workflow conserva el `minimum_required_version` anterior.

Esto evita que todas las actualizaciones pasen a ser obligatorias por accidente.

## Recuperacion ante errores

### Borrar un tag local

```powershell
git tag -d vX.Y.Z
```

### Borrar un tag remoto

```powershell
git push origin :refs/tags/vX.Y.Z
```

### Volver a ejecutar el workflow

Opciones:

1. Desde GitHub Actions, usa `Re-run jobs` si el tag y el commit siguen siendo correctos.
2. Usa `workflow_dispatch` indicando el tag exacto `vX.Y.Z`.

Si el script local termina antes de poder sincronizar porque el workflow tarda demasiado, actualiza tu repo local con:

```powershell
git pull --ff-only origin main
```

### Si falla antes de crear la Release

1. Corrige el error local o en el workflow.
2. Si ya existe el commit de preparacion pero no quieres mantenerlo, crea un commit correctivo o un nuevo tag valido.
3. Si el tag se llego a subir y quieres repetir desde cero, borra primero el tag local y remoto.

### Si la Release existe pero `version.json` no se actualizo

1. Revisa el job fallido y confirma si el asset publica responde.
2. Corrige el problema en `main`.
3. Reejecuta el workflow con `workflow_dispatch` usando el mismo tag si la Release sigue siendo la correcta.
4. Si el workflow sigue fallando por la comprobacion de Release existente, actualiza `updates/version.json` manualmente en un commit controlado y corrige el workflow antes de la siguiente publicacion.

### Si aparece una URL 404 del asset

1. Comprueba que la Release existe.
2. Comprueba que el asset se llama exactamente `Setup_Gest2A3Eco_X.Y.Z.exe`.
3. Comprueba que el tag es `vX.Y.Z` con `v` minuscula.
4. Comprueba que la URL sigue el patron:

```text
https://github.com/jjdominguez79/Gest2A3Eco/releases/download/vX.Y.Z/Setup_Gest2A3Eco_X.Y.Z.exe
```

5. Si el nombre del asset es incorrecto, elimina la Release y el tag, corrige el problema y publica de nuevo.

### Revisar logs de GitHub Actions

1. Abre el repositorio en GitHub.
2. Ve a `Actions`.
3. Entra en la ejecucion del workflow `Publicar version`.
4. Revisa el paso exacto que ha fallado.
5. Descarga los logs si necesitas auditoria.

## Archivos implicados

- `publicar_version.ps1`
- `publicar_version.bat`
- `.github/workflows/publicar-version.yml`
- `release_utils.py`
- `updates/release_metadata.json` en cada publicacion
- `updates/version.json`

## Comandos rapidos de referencia

```powershell
.\publicar_version.ps1
```

```powershell
git tag -d vX.Y.Z
```

```powershell
git push origin :refs/tags/vX.Y.Z
```

```powershell
git fetch origin
git checkout main
git pull --ff-only origin main
```
