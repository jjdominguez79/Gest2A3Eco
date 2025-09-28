# Gest2A3Eco

Aplicación de escritorio en **Python (Tkinter)** para generar ficheros `suenlace.dat` compatibles con **A3ECO**, a partir de extractos bancarios y facturas en Excel.

## ✨ Funcionalidades principales

- **Gestión por empresa**:
  - Selección de empresa al iniciar.
  - Configuración propia de Excel (mapa columnas, primera fila, condiciones).
- **Plantillas**:
  - Bancos: subcuenta banco, subcuenta por defecto, conceptos con comodín `*`.
  - Facturas emitidas: configuración cuentas de clientes, ingresos, IVA repercutido y retenciones.
  - Facturas recibidas: configuración cuentas de proveedores, gastos, IVA soportado y retenciones.
- **Edición sencilla**:
  - Interfaces tipo **tabla** para definir:
    - Mapeo de columnas (Clave → Letra).
    - Conceptos → Subcuentas (Bancos).
    - Tipos de IVA → Cuentas contables (Emitidas/Recibidas).
- **Importación Excel**:
  - Selección de archivo y hoja.
  - Vista previa de datos (primeras 200 filas).
- **Generación de `suenlace.dat`**:
  - Bancos: 2 líneas por apunte (I/U).
  - Facturas: agrupación por Serie+Número y soporte para varios tipos de IVA en una factura.
  - Importes siempre positivos, el signo lo marca **D/H**.
  - Nombre del fichero: `CODIGO_EMPRESA.dat`.

## 📂 Estructura del proyecto

```
Gest2A3Eco/
│── main.py
│── ui_seleccion_empresa.py
│── ui_plantillas.py
│── ui_procesos.py
│── gestor_plantillas.py
│── generador_suenlace.py
│── facturas_common.py
│── facturas_emitidas.py
│── facturas_recibidas.py
│── utilidades.py
│── config.json
│── requirements.txt
│── README.md
└── plantillas/
    └── plantillas.json
```

## ⚙️ Requisitos

- Python 3.9 o superior
- Librerías:
  - `pandas`
  - `openpyxl`

Instalación rápida:

```bash
pip install -r requirements.txt
```

## ▶️ Uso

1. Ejecuta la aplicación:
   ```bash
   python main.py
   ```
2. Selecciona la **empresa**.
3. Configura las **plantillas** de Bancos / Facturas emitidas / Facturas recibidas.
4. Importa el Excel desde la pestaña **Generar enlace**.
5. Elige la plantilla, revisa la vista previa y pulsa **Generar**.
6. Se guardará un fichero `CODIGO_EMPRESA.dat` listo para importar en A3ECO.

## 🛠️ Distribución como ejecutable

### Windows

Para generar un `.exe` con **PyInstaller**:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icono.ico main.py
```

- El icono del ejecutable (`icono.ico`) puede ser distinto al logotipo de la app.
- El `.exe` resultante estará en la carpeta `dist/`.

### macOS

Para generar un `.app` ejecutable en Mac:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icono.icns main.py
```

- El icono debe estar en formato `.icns`.
- El resultado aparecerá en la carpeta `dist/` como una aplicación `.app`.

### Notas

- Se recomienda ubicar el `plantillas.json` en una carpeta compartida para uso multiusuario.
- Para distribuir la aplicación, basta con entregar el ejecutable junto con el archivo de plantillas.

## 📌 Estado actual

- ✅ Configuración mediante tablas (no requiere editar JSON manualmente).
- ✅ Soporte bancos, facturas emitidas y recibidas.
- ✅ Multi-IVA por factura.
- ⏳ Pendiente: exportación/importación de configuraciones a CSV desde la interfaz.

---

👨‍💻 Desarrollado para facilitar la integración entre extractos bancarios, facturas y A3ECO.
