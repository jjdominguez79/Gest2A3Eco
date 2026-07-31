from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from services.maestro_contable_empresa_service import MaestroContableEmpresaService
from services.maestro_terceros_service import MaestroTercerosService


EMPRESA_DGT = "E00006"
SERIE_DGT = "TR"
IVA_HONORARIOS = Decimal("21")
CUENTA_HONORARIOS = "70000000"
CUENTA_SUPLIDOS = "55509999"


def _importe(value, nombre: str, *, obligatorio: bool = False) -> Decimal:
    raw = str(value if value is not None else "").strip()
    raw = raw.replace(".", "").replace(",", ".") if "," in raw else raw
    if not raw:
        if obligatorio:
            raise ValueError(f"Indica el importe de {nombre}.")
        return Decimal("0.00")
    try:
        importe = Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"El importe de {nombre} no es valido.") from exc
    if importe < 0:
        raise ValueError(f"El importe de {nombre} no puede ser negativo.")
    if obligatorio and importe == 0:
        raise ValueError(f"El importe de {nombre} debe ser mayor que cero.")
    return importe


class TramitesDgtFacturacionService:
    def __init__(self, gestor):
        self.gestor = gestor
        self._terceros = MaestroTercerosService()
        self._maestro = MaestroContableEmpresaService()

    def crear_borrador(
        self,
        expediente: dict,
        *,
        destinatario: str,
        honorarios,
        tasa_dgt=0,
        impuesto_620=0,
        otros_suplidos=0,
    ) -> dict:
        expediente_id = str(expediente.get("id") or "").strip()
        if not expediente_id:
            raise ValueError("El expediente no tiene identificador.")
        existente = self.gestor.get_dgt_factura(expediente_id)
        if existente:
            raise ValueError("Este expediente ya tiene una factura vinculada.")

        rol = str(destinatario or "").strip().lower()
        if rol not in {"comprador", "vendedor"}:
            raise ValueError("El destinatario debe ser el comprador o el vendedor.")
        parte = dict(expediente.get(f"{rol}_payload") or {})
        parte.setdefault("nombre", expediente.get(f"{rol}_nombre"))
        parte.setdefault("email", expediente.get(f"{rol}_email"))
        parte.setdefault("telefono", expediente.get(f"{rol}_telefono"))
        nombre = str(parte.get("nombre") or parte.get("nombre_razon_social") or "").strip()
        nif = str(parte.get("nif") or parte.get("nif_cif") or "").strip()
        if not nombre or not nif:
            raise ValueError(f"Faltan el nombre o el NIF/CIF del {rol}.")

        hon = _importe(honorarios, "honorarios", obligatorio=True)
        tasa = _importe(tasa_dgt, "tasa DGT")
        impuesto = _importe(impuesto_620, "impuesto 620")
        otros = _importe(otros_suplidos, "otros suplidos")

        hoy = date.today()
        ejercicio = hoy.year
        empresa = self.gestor.get_empresa(EMPRESA_DGT, ejercicio) or self.gestor.get_empresa(EMPRESA_DGT)
        if not empresa:
            raise ValueError("No existe la empresa E00006 para emitir la factura.")
        ejercicio = int(empresa.get("ejercicio") or ejercicio)
        self._asegurar_serie(ejercicio)
        tercero, subcuenta = self._asegurar_cliente(parte, nombre, nif, empresa)

        matricula = str(expediente.get("vehiculo_matricula") or "").strip()
        referencia = str(expediente.get("referencia") or expediente_id).strip()
        concepto = "Honorarios por cambio de titularidad DGT"
        if matricula:
            concepto += f" - {matricula}"
        lineas = [self._linea(concepto, hon, IVA_HONORARIOS, "honorario", CUENTA_HONORARIOS)]
        for texto, importe in (
            ("Suplido: tasa DGT", tasa),
            ("Suplido: impuesto modelo 620", impuesto),
            ("Otros suplidos del tramite", otros),
        ):
            if importe:
                lineas.append(self._linea(texto, importe, Decimal("0"), "suplido", CUENTA_SUPLIDOS))

        factura_id = str(uuid4())
        factura = {
            "id": factura_id,
            "codigo_empresa": EMPRESA_DGT,
            "ejercicio": ejercicio,
            "tercero_id": tercero["id"],
            "serie": SERIE_DGT,
            "numero": "",
            "fecha_asiento": hoy.isoformat(),
            "fecha_expedicion": hoy.isoformat(),
            "fecha_operacion": hoy.isoformat(),
            "tipo_operacion": "01",
            "modelo_fiscal": "01",
            "nif": nif,
            "nombre": nombre,
            "descripcion": f"Tramite DGT {referencia}",
            "observaciones": f"Factura vinculada al expediente DGT {referencia}.",
            "subcuenta_cliente": subcuenta,
            "subcuenta_ingreso": CUENTA_HONORARIOS,
            "retencion_aplica": 0,
            "moneda_codigo": "EUR",
            "moneda_simbolo": "EUR",
            "generada": 0,
            "enviado": 0,
            "borrador": 1,
            "lineas": lineas,
        }
        self.gestor.upsert_factura_emitida(factura)
        try:
            self.gestor.upsert_dgt_factura({
                "expediente_id": expediente_id,
                "factura_id": factura_id,
                "codigo_empresa": EMPRESA_DGT,
                "ejercicio": ejercicio,
                "destinatario": rol,
                "honorarios": float(hon),
                "tasa_dgt": float(tasa),
                "impuesto_620": float(impuesto),
                "otros_suplidos": float(otros),
            })
        except Exception:
            self.gestor.conn.execute("DELETE FROM facturas_emitidas_docs WHERE id=?", (factura_id,))
            self.gestor.conn.commit()
            raise
        return factura

    def _asegurar_serie(self, ejercicio: int) -> None:
        series = self.gestor.listar_series_emitidas(EMPRESA_DGT, ejercicio)
        if not any(str(item.get("nombre") or "").upper() == SERIE_DGT for item in series):
            self.gestor.upsert_serie_emitida(EMPRESA_DGT, ejercicio, SERIE_DGT, 1, 0, 1)

    def _asegurar_cliente(self, parte: dict, nombre: str, nif: str, empresa: dict) -> tuple[dict, str]:
        tercero = self._terceros.crear_tercero_global(self.gestor, {
            "nif": nif,
            "nombre": nombre,
            "direccion": parte.get("direccion") or "",
            "codigo_postal": parte.get("codigo_postal") or parte.get("cp") or "",
            "poblacion": parte.get("poblacion") or "",
            "provincia": parte.get("provincia") or "",
            "telefono": parte.get("telefono") or "",
            "email": parte.get("email") or "",
            "origen": "tramites_dgt",
        })
        relacion = self.gestor.get_tercero_empresa(EMPRESA_DGT, tercero["id"], int(empresa.get("ejercicio") or 0)) or {}
        subcuenta = str(relacion.get("subcuenta_cliente") or "").strip()
        if not subcuenta:
            digitos = int(empresa.get("digitos_plan") or 8)
            subcuenta = self._maestro.proponer_siguiente_subcuenta(self.gestor, EMPRESA_DGT, "cliente", digitos)
            self._maestro.crear_subcuenta_empresa(self.gestor, {
                "codigo_empresa": EMPRESA_DGT,
                "subcuenta": subcuenta,
                "nombre_subcuenta": nombre,
                "tipo_subcuenta": "cliente",
                "tercero_id": tercero["id"],
                "nif": nif,
                "origen": "tramites_dgt",
            })
        self.gestor.upsert_tercero_empresa({
            **relacion,
            "codigo_empresa": EMPRESA_DGT,
            "tercero_id": tercero["id"],
            "subcuenta_cliente": subcuenta,
            "subcuenta_ingreso": relacion.get("subcuenta_ingreso") or CUENTA_HONORARIOS,
        })
        return tercero, subcuenta

    @staticmethod
    def _linea(concepto: str, base: Decimal, pct_iva: Decimal, tipo: str, cuenta: str) -> dict:
        cuota = (base * pct_iva / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "concepto": concepto,
            "unidades": 1.0,
            "precio": float(base),
            "base": float(base),
            "pct_iva": float(pct_iva),
            "cuota_iva": float(cuota),
            "pct_re": 0.0,
            "cuota_re": 0.0,
            "pct_irpf": 0.0,
            "cuota_irpf": 0.0,
            "tipo": tipo,
            "cuenta_ingreso": cuenta,
        }
