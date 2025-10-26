# Gest2A3Eco

Build con configuración por plantilla, uso concurrente seguro (locks) y nombre de salida único si existe `CODIGO_EMPRESA.dat`.

## Requisitos
```bash
pip install -r requirements.txt
```

## Ejecutar
```bash
python main.py
```

## Generar EXE (Windows)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icono.ico main.py
```

## Generar APP (macOS)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icono.icns main.py
```
