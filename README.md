# Gest2A3Eco

Aplicacion de escritorio en **Python / Tkinter** para Windows que cubre dos funcionalidades principales:

1. **Generacion de `suenlace.dat`** — fichero binario en formato A3ECO a partir de extractos Excel de bancos, facturas emitidas y facturas recibidas.
2. **Gestion interna de facturas emitidas** — creacion, edicion, numeracion automatica, generacion de PDF desde plantilla Word y envio por email o WhatsApp.

---

## Requisitos

- Python 3.10+
- Windows (usa `os.startfile`, `icono.ico` y rutas Win32)
- Dependencias Python: ver `requirements.txt`

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Dependencias principales: `pandas`, `openpyxl`, `xlrd`, `python-docx`, `docxtpl`, `docx2pdf`, `pypdf`, `pillow`, `portalocker`.

---

## Ejecucion en desarrollo

```bash
python main.py
```

## Compilar a .exe

```bash
pyinstaller Gest2A3Eco.spec
# Salida: dist/Gest2A3Eco/Gest2A3Eco.exe
```

---

## Flujo de arranque

```
main.py → login (ui_auth.py) → UISeleccionEmpresa → AppController
  → Notebook con pestanas:
      · Plantillas
      · Facturas emitidas
      · Generar ficheros
```

Los datos de la asesoria (nombre, CIF, contacto) estan en `main.py`.

---

## Arquitectura (MVC por capas)

```
views/ui_*.py               Pantallas Tkinter (solo UI, sin logica de negocio)
controllers/*.py            Coordinadores: navegacion, acciones, validaciones
procesos/*.py               Logica de dominio: generacion de registros A3ECO y PDFs
models/gestor_sqlite.py     Capa de datos SQLite (fuente de verdad)
models/facturas_common.py   Renderizadores A3ECO compartidos y normalizacion de fechas
services/                   Auth, email, importacion de empresas, mapeo Excel
utils/                      Config I/O, validacion de cuentas, formateo numerico
```

### Controladores

| Archivo | Responsabilidad |
|---|---|
| `app_controller.py` | Hub de navegacion principal, carga empresa activa |
| `ui_facturas_emitidas_controller.py` | CRUD facturas emitidas, PDF, envio, suenlace |
| `factura_dialog_controller.py` | Logica del dialogo de edicion de factura |
| `ui_plantillas_controller.py` | Gestion de plantillas de mapeo Excel |
| `ui_procesos_controller.py` | Generacion de suenlace.dat (bancos, emitidas, recibidas) |
| `terceros_empresa_controller.py` | Maestro de terceros por empresa |
| `terceros_global_controller.py` | Maestro de terceros global |
| `user_admin_controller.py` | Administracion de usuarios y permisos |

### Vistas

| Archivo | Pantalla |
|---|---|
| `ui_auth.py` | Login |
| `ui_dashboard_empresa.py` | Dashboard / seleccion de empresa |
| `ui_facturas_emitidas.py` | Lista y edicion de facturas emitidas |
| `ui_plantillas.py` | Gestion de plantillas Excel |
| `ui_procesos.py` | Generacion de ficheros suenlace |
| `ui_empresa_dialog.py` | Dialogo de configuracion de empresa |
| `ui_panel_general.py` | Panel de configuracion general |
| `ui_config_monedas.py` | Configuracion de monedas |
| `ui_user_admin.py` | Administracion de usuarios |
| `ui_theme.py` | Temas visuales Tkinter |

---

## Almacenamiento de datos

**SQLite** en `plantillas/gest2a3eco.db` (se crea en el primer arranque).

Tablas principales:

| Tabla | Contenido |
|---|---|
| `empresas` | Configuracion por empresa y ejercicio: digitos del plan, series de numeracion, prefijos de cuentas |
| `series_emitidas` | Series de facturacion por empresa/ejercicio (`es_rectificativa` distingue serie normal de rectificativa) |
| `facturas_emitidas` | Facturas emitidas con cabecera, lineas (JSON), rutas PDF y estado de generacion/envio |
| `facturas_recibidas` | Facturas recibidas importadas desde Excel |
| `terceros` | Maestro global de clientes/proveedores con NIF y datos de contacto |
| `terceros_empresas` | Subcuenta contable por tercero y empresa |
| `bancos` | Plantillas de movimientos bancarios |
| `plan_cuentas` | Plan contable por empresa |
| `usuarios` | Usuarios de la aplicacion (hash scrypt) |
| `usuarios_empresas` | Permisos por usuario y empresa (NINGUNO / LECTURA / ESCRITURA) |

---

## Facturas emitidas — funcionalidades

### Tipos de facturas
- **Factura normal**: serie configurable por empresa (por defecto `A`).
- **Factura rectificativa**: se puede crear de dos formas:
  - **Nueva Rectif.** — factura rectificativa en blanco con serie `R` y numeracion propia.
  - **Rectificar** — copia de una factura existente con lineas negadas (importe invertido).

### Numeracion automatica
- Cada empresa tiene contadores independientes para facturas normales y rectificativas.
- El numero se asigna al confirmar (no al guardar como borrador).
- Los borradores se pueden confirmar masivamente.

### Generacion de PDF
Todos los PDFs se generan **siempre desde la plantilla Word** (`plantilla.docx` en la carpeta de la empresa). No existe fallback a PDF basico.

- **Exportar PDF**: muestra dialogo de guardado; guarda tambien copia en `pdfs_emitidas/<empresa>/`.
- **Abrir PDF**: si el fichero no existe en `pdfs_emitidas/`, lo genera automaticamente y lo abre.
- **Compartir PDF**: igual que abrir, luego permite enviar por email (SMTP) o WhatsApp.
- **PDF seleccion**: combina multiples facturas marcadas en un unico PDF usando `pypdf`.

La carpeta A3ECO (`Z:\A3\A3ECO\<cod>\FACTURAS\`) **solo recibe PDFs al generar el suenlace.dat**, no durante el flujo normal de exportacion.

### Envio
- **Email**: via SMTP configurado en la aplicacion (soporte HTML con template personalizable en `plantillas/email_factura.html`).
- **WhatsApp**: abre `wa.me/` en el navegador y muestra el PDF en el explorador de archivos.

### Generacion de suenlace.dat
El fichero binario A3ECO incluye:
- Registro tipo 1/cabecera de factura emitida (256 o 512 bytes).
- Registros tipo 9/detalle por cada linea.
- Registro tipo C/alta de cuenta si procede.
- Registro tipo 6/identificador de origen (trazabilidad Gest2A3Eco → A3ECO), con `app_id = "G2A"`.
- PDF copiado a la carpeta de enlace contable de A3ECO.

---

## Formato binario A3ECO

`models/facturas_common.py` centraliza todos los renderizadores de registros.

| Tipo | Descripcion | Tamano |
|---|---|---|
| 0 | Movimiento bancario | 512 bytes |
| 1 | Cabecera factura emitida | 256 / 512 bytes |
| 2 | Cabecera factura recibida | 254 bytes |
| 9 | Detalle / linea de factura | 256 / 254 bytes |
| C | Alta de cuenta en plan | variable |
| 6 | Identificador de origen (trazabilidad) | 256 / 512 bytes |

**Reglas clave:**
- La longitud de subcuenta es configurable por empresa (`digitos_plan`, por defecto 8).
- El campo fecha acepta `date`, `datetime`, `pandas.Timestamp`, serial Excel y cadenas; las fechas invalidas producen `"00000000"`.
- Las facturas se agrupan por `Numero Factura Largo SII` (si existe) o por `Serie + Numero`.

---

## Autenticacion y permisos

- `services/auth_service.py`: hashing con **scrypt**, roles `ADMIN / EMPLEADO / CLIENTE`.
- `services/secured_gestor.py`: envuelve `GestorSQLite` con verificacion de rol y permiso por empresa.
- Permisos por empresa: `NINGUNO / LECTURA / ESCRITURA`.

---

## Servicios auxiliares

| Archivo | Funcion |
|---|---|
| `services/email_service.py` | Envio SMTP, template HTML de email, configuracion persistida |
| `services/empresa_service.py` | Logica de empresa activa y configuracion |
| `services/excel_mapping.py` | Extraccion de filas desde Excel segun mapeo de plantilla |
| `services/import_a3_empresa.py` | Importacion de empresas desde ficheros A3ECO |
| `services/import_empresas_csv.py` | Importacion masiva de empresas desde CSV |

---

## Estructura de carpetas

```
Gest2A3Eco/
├── main.py                     Punto de entrada (datos de asesoria aqui)
├── controllers/                Logica de negocio y coordinacion
├── views/                      Pantallas Tkinter
├── procesos/                   Generadores A3ECO y PDF
│   ├── bancos.py               Movimientos bancarios
│   ├── facturas_emitidas.py    Registros A3ECO de emitidas
│   ├── facturas_recibidas.py   Registros A3ECO de recibidas
│   └── facturas_word.py        Generacion de PDF desde plantilla Word
├── models/
│   ├── gestor_sqlite.py        Capa de datos SQLite
│   └── facturas_common.py      Renderizadores A3ECO y utilidades compartidas
├── services/                   Auth, email, importacion
├── utils/
│   ├── utilidades.py           Formateo numerico, config I/O
│   └── validaciones.py         Validacion y normalizacion de NIF/CIF
├── plantillas/
│   ├── gest2a3eco.db           Base de datos SQLite
│   └── email_factura.html      Template HTML para emails de factura
├── pdfs_emitidas/              PDFs generados (por empresa)
├── assets/                     Recursos graficos
├── Helpers/                    Scripts de mantenimiento / migracion (no parte del flujo principal)
├── requirements.txt
├── Gest2A3Eco.spec             Configuracion PyInstaller
└── CONTEXT.md                  Notas tecnicas y checklist de pruebas manuales
```

---

## Convenciones de desarrollo

- **Idioma**: español en identificadores, UI y comentarios. Ficheros fuente ASCII (sin acentos).
- **Capas**: UI en `views/`, logica en `controllers/` y `procesos/`, datos en `models/`. No mezclar.
- **PDF**: siempre via `facturas_word.py` → `generar_pdf_desde_plantilla_word()`. Sin fallback a PDF basico.
- **SQLite**: operar directamente con `GestorSQLite`; `plantillas.json` solo para seed inicial.
- **`main.py`**: no modificar salvo cambio de datos de la asesoria.
- **Copias de seguridad**: hacer backup de `plantillas/` antes de migraciones de esquema.
