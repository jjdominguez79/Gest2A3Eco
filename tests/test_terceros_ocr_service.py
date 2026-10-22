from services.terceros_ocr_service import TercerosOcrService


class GestorTercerosPrueba:
    def __init__(self):
        self.tipos_solicitados = None

    def listar_subcuentas_facturacion(self, _codigo, tipos, activo=True):
        self.tipos_solicitados = tuple(tipos)
        assert activo is True
        return [
            {
                "tercero_id": "tercero-a3",
                "tercero_nif": "16511073V",
                "tercero_nombre_legal": "ELISA DE GREGORIO GARCIA",
                "tipo_subcuenta": "proveedor",
                "subcuenta": "40000008",
            }
        ]

    def listar_terceros_por_empresa(self, _codigo, _ejercicio):
        return [
            {
                "id": "tercero-legacy",
                "nif": "B12345678",
                "nombre": "PROVEEDOR LEGACY",
                "subcuenta_proveedor": "40000009",
            }
        ]

    def listar_terceros(self):
        return []


class GestorAltaOcrPrueba:
    def __init__(self):
        self.terceros = []
        self.relacion = None
        self.maestro = []

    def get_empresa(self, _codigo, _ejercicio):
        return {"digitos_plan": 8}

    def listar_maestro_subcuentas_empresa(self, _codigo, activo=None):
        assert activo is None
        return list(self.maestro)

    def listar_terceros_por_empresa(self, _codigo, _ejercicio):
        return []

    def get_plan_cuentas(self, _codigo, _ejercicio):
        return [{"cuenta": "40000001"}, {"cuenta": "60000000"}]

    def listar_terceros(self):
        return list(self.terceros)

    def get_maestro_subcuenta_por_subcuenta(self, _codigo, subcuenta):
        return next(
            (item for item in self.maestro if item["subcuenta"] == subcuenta),
            None,
        )

    def upsert_tercero(self, tercero):
        item = dict(tercero)
        item["id"] = str(item.get("id") or "tercero-ocr")
        self.terceros = [
            actual for actual in self.terceros
            if str(actual.get("id")) != item["id"]
        ]
        self.terceros.append(item)
        return item["id"]

    def get_tercero_empresa(self, _codigo, _tercero_id, _ejercicio):
        return dict(self.relacion) if self.relacion else None

    def upsert_tercero_empresa(self, relacion):
        self.relacion = dict(relacion)

    def upsert_maestro_subcuenta(self, cuenta):
        self.maestro = [
            item for item in self.maestro
            if item["subcuenta"] != cuenta["subcuenta"]
        ]
        self.maestro.append(dict(cuenta))


def test_candidatos_empresa_incluyen_maestro_a3_y_legacy():
    gestor = GestorTercerosPrueba()
    servicio = TercerosOcrService()

    candidatos = servicio.listar_candidatos_empresa(
        gestor, "E00001", 2026, ("proveedor", "acreedor"),
    )

    assert gestor.tipos_solicitados == ("proveedor", "acreedor")
    assert candidatos[0]["id"] == "tercero-a3"
    assert candidatos[0]["nombre"] == "ELISA DE GREGORIO GARCIA"
    assert candidatos[0]["nif"] == "16511073V"
    assert candidatos[0]["subcuenta_proveedor"] == "40000008"
    assert candidatos[1]["id"] == "tercero-legacy"


def test_resolver_tercero_usa_el_mismo_maestro_que_el_selector():
    tercero = TercerosOcrService().resolver_tercero(
        GestorTercerosPrueba(), "16511073-V", "", "E00001", 2026,
    )

    assert tercero is not None
    assert tercero["id"] == "tercero-a3"
    assert tercero["subcuenta_proveedor"] == "40000008"


def test_alta_ocr_propone_primera_subcuenta_libre_del_plan_generico():
    gestor = GestorAltaOcrPrueba()

    propuesta = TercerosOcrService().proponer_subcuenta(
        gestor, "proveedor", "E00001", 2026,
    )

    assert propuesta == "40000002"


def test_alta_ocr_crea_tercero_relacion_y_subcuenta_con_datos_detectados():
    gestor = GestorAltaOcrPrueba()

    tercero = TercerosOcrService().crear_tercero(
        gestor,
        {"nif": "B12345678", "nombre": "PROVEEDOR OCR SL"},
        "40000002",
        "proveedor",
        "E00001",
        2026,
    )

    assert tercero["id"] == "tercero-ocr"
    assert tercero["nif"] == "B12345678"
    assert tercero["nombre"] == "PROVEEDOR OCR SL"
    assert tercero["subcuenta_proveedor"] == "40000002"
    assert gestor.relacion["tercero_id"] == "tercero-ocr"
    assert gestor.relacion["subcuenta_proveedor"] == "40000002"
    assert gestor.relacion["proveedor_tipo_operacion_iva"] == "INTERIOR_DEDUCIBLE"
    cuenta = gestor.get_maestro_subcuenta_por_subcuenta("E00001", "40000002")
    assert cuenta["tercero_id"] == "tercero-ocr"
    assert cuenta["nif_snapshot"] == "B12345678"
    assert cuenta["nombre_subcuenta"] == "PROVEEDOR OCR SL"
    assert cuenta["pendiente_alta_a3"] == 1


def test_alta_ocr_conserva_ficha_y_configuracion_de_un_tercero_existente():
    gestor = GestorAltaOcrPrueba()
    gestor.terceros = [{
        "id": "tercero-existente",
        "nif": "B12345678",
        "nombre": "NOMBRE ANTERIOR",
        "direccion": "Calle Mayor 1",
        "email": "facturas@proveedor.test",
    }]
    gestor.relacion = {
        "codigo_empresa": "E00001",
        "tercero_id": "tercero-existente",
        "subcuenta_gasto": "60000000",
        "proveedor_tipo_operacion_iva": "INTERIOR_NO_DEDUCIBLE",
    }

    TercerosOcrService().crear_tercero(
        gestor,
        {"nif": "B12345678", "nombre": "NOMBRE DETECTADO"},
        "40000002",
        "proveedor",
        "E00001",
        2026,
    )

    assert gestor.terceros[0]["nombre"] == "NOMBRE DETECTADO"
    assert gestor.terceros[0]["direccion"] == "Calle Mayor 1"
    assert gestor.terceros[0]["email"] == "facturas@proveedor.test"
    assert gestor.relacion["subcuenta_gasto"] == "60000000"
    assert gestor.relacion["proveedor_tipo_operacion_iva"] == "INTERIOR_NO_DEDUCIBLE"
