"""
Prueba/calibracion de obtencion de un certificado administrativo (Opcion A).

Abre la sede del organismo con el certificado del cliente y, en modo aprendizaje,
te deja navegar a mano hasta el certificado y descargarlo, guardando capturas +
HTML en ./logs para fijar el flujo definitivo.

Uso (desde la raiz del proyecto):
    python Helpers/probar_certificado.py --pfx "C:\\ruta\\cliente.pfx" --password "***" \
        --tipo TGSS_CORRIENTE --naf 281234567840 --login-manual 150

Tipos: TGSS_CORRIENTE, TGSS_COTIZACION, AEAT_CORRIENTE, AEAT_CENSAL, AEAT_IAE.

Requisitos:  pip install cryptography playwright && playwright install chromium
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.aapp.base import OpcionesSync                       # noqa: E402
from services.aapp.cert_store import CertMaterial                 # noqa: E402
from services.aapp.certificados import TIPOS, obtener_proveedor   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Prueba de obtencion de certificado")
    ap.add_argument("--pfx", required=True)
    ap.add_argument("--password", default="")
    ap.add_argument("--tipo", required=True, choices=list(TIPOS.keys()))
    ap.add_argument("--naf", default="")
    ap.add_argument("--ccc", action="append", default=[], help="CCC (se puede repetir)")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--login-manual", type=int, default=0, metavar="SEG")
    ap.add_argument("--cliente-nombre", default="",
                    help="Si se indica, guarda en la carpeta de RED del cliente (patron de produccion).")
    ap.add_argument("--cif", default="", help="CIF del cliente para el nombre del PDF.")
    args = ap.parse_args()

    if not os.path.isfile(args.pfx):
        print("ERROR: no existe", args.pfx)
        return 2

    material = CertMaterial(cert_id="test", nombre=os.path.basename(args.pfx),
                            nif_titular=None, ruta_archivo=args.pfx, password=args.password)
    headed = args.headed or args.login_manual > 0
    opciones = OpcionesSync(
        headless=not headed,
        modo_diagnostico=True,
        carpeta_diagnostico=os.path.join(os.getcwd(), "logs"),
        carpeta_descargas=os.path.join(os.getcwd(), "logs"),
        pausa_login_segundos=args.login_manual,
        datos_ss={"naf": args.naf or None, "cccs": args.ccc},
        log=lambda m: print(m),
    )
    if args.cliente_nombre:
        from services.aapp.certificados import (_carpeta_base_certificados,
                                                _safe_nombre, ruta_pdf_certificado)
        carpeta = os.path.join(_carpeta_base_certificados(), _safe_nombre(args.cliente_nombre))
        try:
            os.makedirs(carpeta, exist_ok=True)
        except Exception as exc:
            print(f"AVISO: no se pudo crear la carpeta de red ({exc}); se usara logs.")
        else:
            opciones.carpeta_descargas = carpeta
            opciones.ruta_pdf_destino = ruta_pdf_certificado(carpeta, args.tipo, args.cif)
            print(f"[dest] se guardara en: {opciones.ruta_pdf_destino}")
    prov = obtener_proveedor(args.tipo)
    if prov is None:
        print("No hay proveedor para", args.tipo)
        return 3
    print(f"[cert] tipo={args.tipo} organismo={TIPOS[args.tipo][0]}  NAF={args.naf or '-'}  CCC={args.ccc or '-'}")
    res = prov.obtener(material, args.tipo, opciones)
    print(f"\n[resultado] estado={res.estado} ok={res.ok} resultado={res.resultado} pdf={res.pdf_path}")
    print("mensaje:", res.mensaje)
    if res.error_detalle:
        print("\n[error]\n" + res.error_detalle)
    print("\nRevisa ./logs (cert_*.png / cert_*.html) para ajustar el flujo del portal.")
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
