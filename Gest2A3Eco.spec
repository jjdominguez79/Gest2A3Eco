# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files


python_root = Path(sys.base_prefix)
python_dlls = python_root / 'DLLs'
python_tcl = python_root / 'tcl'


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        (str(python_dlls / '_tkinter.pyd'), '.'),
        (str(python_dlls / 'tcl86t.dll'), '.'),
        (str(python_dlls / 'tk86t.dll'), '.'),
    ],
    datas=[
        ('logo.png', '.'),
        ('icono.ico', '.'),
        (str(python_root / 'Lib' / 'tkinter'), 'tkinter'),
        (str(python_tcl / 'tcl8.6'), '_tcl_data'),
        (str(python_tcl / 'tk8.6'), '_tk_data'),
        # XSD oficial de Facturae 3.2.1 usado por
        # services/facturae/facturae_validator.py para validar cada XML
        # generado. PyInstaller no incluye ficheros no-Python automaticamente.
        ('services/facturae/schemas', 'services/facturae/schemas'),
    ] + collect_data_files('tkinterdnd2'),
    hiddenimports=[
        'keyring',
        'keyring.backends',
        'keyring.backends.Windows',
        'tkinterdnd2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hooks/runtime_tkinter.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Gest2A3Eco',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icono.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Gest2A3Eco',
)
