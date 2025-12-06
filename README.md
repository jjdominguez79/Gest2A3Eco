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
2) Gestiona plantillas en la pestaña "Plantillas" (mapeo de columnas de Excel).
3) En la pestaña "Generar ficheros":
   - Elige tipo (Bancos, Facturas Emitidas, Facturas Recibidas).
   - Selecciona plantilla, carga Excel y hoja.
   - Revisa el preview y pulsa "Generar Suenlace.dat".
4) Importa el `.dat` generado en A3ECO.

## Compilar a .exe (PyInstaller)
```bash
pyinstaller --name=Gest2A3Eco --icon=icono.ico --onefile --windowed --add-data "logo.png;." main.py
```
El ejecutable quedara en `dist/Gest2A3Eco.exe`.

## Estructura breve
- `main.py`: arranque de la UI.
- `ui_*`: pantallas Tkinter.
- `procesos/`: logica de generacion por tipo (bancos, emitidas, recibidas).
- `plantillas/plantillas.json`: almacenamiento de plantillas (se crea si no existe).

## Notas
- Los datos de la asesoría (nombre, CIF, contacto) estan en `main.py`.
- Las plantillas se guardan por empresa; revisa `plantillas.json` si necesitas hacer backup.
