"""Configura Tcl/Tk en el ejecutable congelado.

PyInstaller 6.17 todavia no detecta correctamente Tcl/Tk en Python 3.14
para Windows, por lo que el spec incluye estos recursos explicitamente.
"""

import os
import sys


if getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.environ["TCL_LIBRARY"] = os.path.join(base, "_tcl_data")
    os.environ["TK_LIBRARY"] = os.path.join(base, "_tk_data")
