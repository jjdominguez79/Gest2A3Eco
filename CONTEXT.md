# CONTEXT

## Resumen ejecutivo
- Gest2A3Eco es una app de escritorio en Python/Tkinter para generar ficheros `suenlace.dat` de A3ECO a partir de Excel y, adem·s, para emitir facturas desde la propia app (PDF y suenlace). Es la evoluciÛn de Gest2Bank, con foco en bancos + facturas emitidas/recibidas.
- Punto de entrada: `main.py` crea la ventana, aplica tema (`views/ui_theme.py`), levanta cabecera y un Notebook con pestaÒas de plantillas, facturas emitidas y generaciÛn de ficheros. Ejecutar con `python main.py`.
- Datos persistentes: SQLite (`plantillas/gest2a3eco.db`) vÌa `GestorSQLite` con semilla opcional desde `plantillas/plantillas.json`. Maestro de terceros, empresas, plantillas y facturas viven en esta BD. `GestorPlantillas` (JSON con portalocker) queda como compatibilidad/semilla; no es el camino real.

## Funcionalidades principales
- **A) Bancos/Excel → suenlace.dat (A3ECO)**  
  - Plantillas por banco (`views/ui_plantillas.py` → `GestorSQLite.upsert_banco`): subcuenta del banco, subcuenta por defecto, lista de patrones de concepto con comodÌn `*` → subcuenta contrapartida.  
  - GeneraciÛn (`views/ui_procesos.py` + `procesos/bancos.py`): lee Excel seg˙n mapeo por letra de columna, crea movimientos tipo 0 (512 bytes) con `models/facturas_common.render_a3_tipo0_bancos`. ValidaciÛn de fecha; filas sin fecha v·lida se omiten y se reportan.
- **B) Plantillas**  
  - Por empresa y ejercicio (`models/gestor_sqlite.py`, tabla `bancos`/`facturas_emitidas`/`facturas_recibidas`).  
  - Configurable: cÛdigo empresa, subcuentas (banco, por defecto), prefijos/subcuentas por defecto para clientes/proveedores, dÌgitos del plan contable, mapeo Excel (`primera_fila_procesar`, `ignorar_filas` estilo `H=0`, `condicion_cuenta_generica` para forzar cuenta genÈrica).  
  - Conceptos con comodÌn `*` (fnmatch) para mapear texto → subcuenta.
- **C) FacturaciÛn**  
  - Plantillas de emitidas/recibidas con cuentas por defecto, prefijos y mapeo Excel (tabla `facturas_emitidas`/`facturas_recibidas`).  
  - EmisiÛn manual de facturas emitidas (`views/ui_facturas_emitidas.py`): alta/ediciÛn/copia, numeraciÛn por serie (`serie_emitidas` + `siguiente_num_emitidas` en tabla `empresas`), asignaciÛn de tercero maestro + subcuenta por empresa (`terceros`/`terceros_empresas`), lÌneas con IVA/IRPF, marcadores de generaciÛn, exportaciÛn a PDF, generaciÛn `suenlace.dat` 256 bytes (cabecera tipo 1 + detalle tipo 9) usando `procesos/facturas_emitidas.py`.  
  - ImportaciÛn desde Excel: pestaÒa "Generar ficheros" admite facturas emitidas y recibidas (`procesos/facturas_recibidas.py` genera cabecera tipo 1/2 + detalle tipo 9, formato 254) a partir de mapeo por letras.

## Arquitectura del cÛdigo
- **UI (Tkinter):** `main.py` (arranque, cabecera, navegaciÛn), `views/ui_seleccion_empresa.py` (CRUD empresa + maestro de terceros), `views/ui_plantillas.py` (gestiÛn de plantillas), `views/ui_procesos.py` (import Excel + generar suenlace), `views/ui_facturas_emitidas.py` (facturas emitidas, PDF, suenlace). Tema visual en `views/ui_theme.py`.
- **Datos:** `models/gestor_sqlite.py` (SQLite; tablas `empresas`, `bancos`, `facturas_emitidas`, `facturas_recibidas`, `facturas_emitidas_docs`, `terceros`, `terceros_empresas`; migraciÛn opcional desde JSON), `models/gestor_plantillas.py` (legacy JSON + portalocker).
- **Dominio/procesado:** `procesos/bancos.py`, `procesos/facturas_emitidas.py`, `procesos/facturas_recibidas.py` generan lÌneas/registros; `models/facturas_common.py` define modelo `Linea`, normaliza fechas y renderiza formatos A3 (512/254/256 bytes); `utils/utilidades.py` valida subcuentas y formatea importes/fechas.
- **Config/build:** `requirements.txt` (pandas, openpyxl, portalocker), `config.json` (ruta JSON legacy), `Gest2A3Eco.spec` (PyInstaller onefile con logo), `icono.ico`/`logo.png`.

## Flujo de usuario (UI real)
- Lanzar `python main.py`. Cabecera fija con datos de asesoria y botones "Empresas" y "Cerrar".
- **Seleccion de empresa (`UISeleccionEmpresa`):** listar empresas; crear/editar/copiar (incrementa ejercicio y reinicia numeraciÛn), eliminar (borra plantillas/facturas/terceros de ese ejercicio), abrir maestro de terceros (subcuentas cliente/proveedor por empresa). Al pulsar "Continuar" carga dashboard.
- **Dashboard (Notebook):**  
  - PestaÒa **Plantillas**: gestionar plantillas de bancos/emitidas/recibidas; editor de mapeo Excel y patrones.  
  - PestaÒa **Facturas emitidas**: CRUD de facturas, selector de tercero maestro, sugerencia de n˙mero (`serie_emitidas` + padding 6), totales, marca de generada, exportar PDF, generar suenlace para selecciÛn usando plantilla de emitidas, marcar generadas con `fecha_generacion`.  
  - PestaÒa **Generar ficheros**: elegir tipo (Bancos/Emitidas/Recibidas), seleccionar plantilla, cargar Excel y hoja (preview en Treeview), generar `suenlace.dat` (pregunta ruta).
- BotÛn "Empresas" en cabecera vuelve a la pantalla de selecciÛn.

## Formatos y reglas de negocio clave
- **Fechas:** `_fecha_yyyymmdd` (`models/facturas_common.py`) acepta date/datetime, `pandas.Timestamp`, seriales Excel 1900/1904 y cadenas; invalida → `00000000`. Filas de bancos sin fecha v·lida se omiten con aviso.
- **DÌgitos plan contable:** por empresa (`empresas.digitos_plan`, default 8). `validar_subcuenta_longitud` fuerza longitud exacta en UI de plantillas/terceros. `_ajustar_cuenta` en recibidas recorta o rellena con ceros a derecha.
- **AsignaciÛn de conceptos (bancos):** `procesos/bancos.py` recorre `conceptos` con patrones `fnmatch` (comodÌn `*`); el primero que matchea define la contrapartida, si no, usa `subcuenta_por_defecto`.
- **Construccion de subcuentas:**  
  - Clientes (emitidas): prefijo `cuenta_cliente_prefijo` + dÌgitos del NIF; si Excel trae subcuenta, se limpia a dÌgitos y se ajusta a `digitos_plan`.  
  - Proveedores (recibidas): prioridad `_cuenta_tercero_override` > fila marcada `_usar_cuenta_generica` (por `condicion_cuenta_generica`) → `cuenta_proveedor_por_defecto` > subcuenta en Excel > prefijo + NIF.  
  - Cuentas IVA/ingreso/gasto/retencion se toman de la plantilla; si faltan, defaults en cÛdigo (700/477/629/472/475...).
- **Agrupacion de facturas:** Emitidas/recibidas agrupan filas por `Numero Factura Largo SII` si existe; si no, por `Serie`+`Numero Factura`. Cada grupo genera cabecera + varias lÌneas de IVA.
- **Nombre de salida:** di·logos de guardado sugieren `E{CODIGO}.dat` (emitidas/recibidas) o `E{CODIGO}.dat` para bancos; el usuario puede cambiarlo. Formatos de registro: bancos tipo 0 (512 bytes), facturas compras/ventas tipo 1/2 + detalle 9 (254 bytes) o 256 bytes para emitidas internas.
- **Ejercicio contable:** se guarda por empresa y se replica al crear/copiar plantillas/terceros/facturas; se usa en claves primarias SQLite.

## Ficheros source of truth
- Base de datos principal: `plantillas/gest2a3eco.db` (SQLite, creado en arranque si falta).  
- Semilla/legacy JSON: `plantillas/plantillas.json` (solo se importa si la BD est· vacÌa). Lock en `plantillas/plantillas.json.lock`.  
- Config legacy: `config.json` (ruta del JSON).  
- Plantillas/ficheros de salida elegidos por el usuario no se versionan; haz copia de la carpeta `plantillas/` antes de cambios.

## Ejecucion local y build
- Requisitos: Python 3.10+, Windows (Tkinter incluido), dependencias `pandas`, `openpyxl`, `portalocker` (`pip install -r requirements.txt`).
- Desarrollo:  
  ```bash
  python -m venv .venv
  .venv\\Scripts\\activate
  pip install -r requirements.txt
  python main.py
  ```
- Build .exe: usar `pyinstaller Gest2A3Eco.spec` o el comando README (`pyinstaller --name=Gest2A3Eco --icon=icono.ico --onefile --windowed --add-data "logo.png;." main.py`). Ejecutable queda en `dist/`.

## Estado actual
- Camino real: `GestorSQLite` + BD en `plantillas/gest2a3eco.db`; `GestorPlantillas` se mantiene solo para compatibilidad y semilla inicial.
- UI de facturas emitidas completa (CRUD, copia, maestro de terceros, numeraciÛn por serie, PDF simple, marca de generadas, suenlace). No hay UI equivalente para facturas recibidas (solo generaciÛn desde Excel en pestaÒa "Generar ficheros").
- Sin tests automatizados; validaciÛn manual necesaria. Main ya contiene datos de cabecera de la asesorÌa en texto plano.
- Worktree actual: `main.py` tiene cambios sin commitear (no revertir).

## Convenciones para contribuir
- Mantener separaciÛn UI (`views/ui_*.py`) vs lÛgica de procesos (`procesos/*.py`) vs datos (`models/gestor_sqlite.py`). No duplicar reglas de negocio; reutilizar helpers de `models/facturas_common.py` y `utils/utilidades.py`.
- Respetar `digitos_plan` y validaciones de subcuentas en nuevas pantallas. Usar el mapeo por letras existente si se amplÌan importaciones.
- Mantener ASCII en nuevos archivos, nomenclatura en castellano como el cÛdigo actual, y evitar tocar `main.py` (datos de cabecera) salvo requerimiento explÌcito.
- Al tocar datos, preferir operar sobre SQLite; si se necesitan seeds, sincronizar `plantillas.json` solo con cuidado.

## Checklist de smoke test
- `python main.py` abre ventana y cabecera con logo y botones.
- Crear empresa dummy, comprobar que aparece en selector y que `plantillas/gest2a3eco.db` se actualiza.
- En pestaÒa Plantillas, crear plantilla de bancos con subcuentas v·lidas y patrones; guardar y reabrir para verificar persistencia.
- En pestaÒa Generar ficheros, cargar Excel sencillo con columnas mapeadas y generar `suenlace.dat` para bancos (validar que se crea fichero y no hay errores de fecha).
- En pestaÒa Facturas emitidas, crear factura con tercero maestro, generar PDF y `suenlace.dat` usando plantilla; verificar que se marca como generada y que la numeraciÛn aumenta.
- Reabrir app y confirmar que datos (empresas, plantillas, facturas, terceros) se cargan desde SQLite sin degradar el flujo.
