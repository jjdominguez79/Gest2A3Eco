# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


PROJECT_DIR = Path.cwd()

datas = [
    (str(PROJECT_DIR / "logo.png"), "."),
    (str(PROJECT_DIR / "icono.ico"), "."),
    (str(PROJECT_DIR / "config.example.json"), "."),
    (str(PROJECT_DIR / "plantillas" / "email_factura.html"), "plantillas"),
]

for asset_path in (PROJECT_DIR / "assets").rglob("*"):
    if asset_path.is_file():
        if asset_path.name.lower() == "thumbs.db":
            continue
        rel_parent = asset_path.relative_to(PROJECT_DIR).parent
        datas.append((str(asset_path), str(rel_parent)))

hiddenimports = [
    "docxtpl",
    "docx2pdf",
    "openpyxl",
    "pandas",
    "pypdf",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "xlrd",
]


a = Analysis(
    ["main.py"],
    pathex=[str(PROJECT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    name="Gest2A3Eco",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_DIR / "icono.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Gest2A3Eco",
)
