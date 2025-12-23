# Gest2A3Eco
Aplicacion de escritorio en **Python (Tkinter)** para generar `suenlace.dat` de A3ECO a partir de Excel (bancos, facturas emitidas y recibidas).

## Requisitos
- Python 3.10+
- Windows (probado en Windows; usa icono `.ico`)
- Dependencias Python: ver `requirements.txt`

Instalacion de dependencias:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Ejecucion en desarrollo
```bash
python main.py
```

## Uso basico
1) Al abrir, selecciona la empresa con la que trabajar (pestana "Empresas").
2) Gestiona plantillas en la pestana "Plantillas" (mapeo de columnas de Excel).
3) (Nuevo) En la pestana "Facturas emitidas" puedes crear/editar/copiar facturas manualmente, elegir clientes desde el maestro de terceros (subcuenta por empresa), exportar a PDF y generar `suenlace.dat` con la plantilla de emitidas.
4) En la pestaña "Generar ficheros":
   - Elige tipo (Bancos, Facturas Emitidas, Facturas Recibidas).
   - Selecciona plantilla, carga Excel y hoja.
   - Revisa el preview y pulsa "Generar Suenlace.dat".
5) Importa el `.dat` generado en A3ECO.

## Compilar a .exe (PyInstaller)
Para un arranque mas rapido usa el modo directorio (evita `--onefile`):
```bash
pyinstaller --name=Gest2A3Eco --icon=icono.ico --windowed --add-data "logo.png;." --add-data "plantilla.docx;." main.py
```
El ejecutable quedara en `dist/Gest2A3Eco/Gest2A3Eco.exe` (junto a sus dependencias).

## Datos y almacenamiento
- Persistencia en SQLite: `plantillas/gest2a3eco.db`.
- Empresas, plantillas, terceros y facturas se guardan en la base de datos (no se usa JSON).

## Estructura breve
- `main.py`: arranque de la UI.
- `ui_*`: pantallas Tkinter.
- `procesos/`: logica de generacion por tipo (bancos, emitidas, recibidas).
- `models/gestor_sqlite.py`: capa de datos SQLite.

## Contexto del proyecto
Consulta `CONTEXT.md` para un panorama actualizado de funcionalidades, arquitectura, reglas de negocio y pasos de ejecucion.

## Notas
- Los datos de la asesoria (nombre, CIF, contacto) estan en `main.py`.
