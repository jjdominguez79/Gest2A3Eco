from pathlib import Path

from models.gestor_sqlite import GestorSQLite
from services.auth_service import AuthService, AuthorizationService
from services.tramites_dgt_repository import ApiDgtRepository
from services.tramites_dgt_service import TramitesDgtService, get_protocol_url_from_argv


class _MemoryDgtRepository:
    def __init__(self):
        self.expedientes = {}
        self.docs = {}
        self.doc_seq = 0

    def listar_expedientes(self):
        return list(self.expedientes.values())

    def get_expediente(self, expediente_id: str):
        item = self.expedientes.get(expediente_id)
        return dict(item) if item else None

    def get_expediente_por_referencia(self, referencia: str):
        for item in self.expedientes.values():
            if item.get("referencia") == referencia:
                return dict(item)
        return None

    def upsert_expediente(self, expediente: dict):
        self.expedientes[expediente["id"]] = dict(expediente)
        return expediente["id"]

    def validar_expediente(self, expediente_id: str, user_id: int):
        item = dict(self.expedientes[expediente_id])
        item["estado"] = "validado"
        item["validado_por"] = user_id
        self.expedientes[expediente_id] = item

    def insertar_documento_generado(self, doc: dict):
        self.doc_seq += 1
        payload = dict(doc, id=self.doc_seq)
        self.docs.setdefault(doc["expediente_id"], []).append(payload)
        return self.doc_seq

    def listar_documentos_generados(self, expediente_id: str):
        return list(self.docs.get(expediente_id, []))


def _tables(gestor: GestorSQLite) -> set[str]:
    rows = gestor.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def _columns(gestor: GestorSQLite, table: str) -> set[str]:
    rows = gestor.conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


class _FirmaClient:
    def __init__(self):
        self.envios = []

    def enviar_documento(self, **kwargs):
        self.envios.append(kwargs)
        return {"uuid": f"firma-{len(self.envios)}", "status": "sent"}

    def consultar(self, request_id):
        return {"uuid": request_id, "status": "signed"}

    def descargar_evidencias(self, request_id, destino, nombre_base):
        base = Path(destino)
        base.mkdir(parents=True, exist_ok=True)
        firmado = base / f"{nombre_base}_firmado.pdf"
        registro = base / f"{nombre_base}_registro_firma.pdf"
        firmado.write_bytes(b"%PDF firmado")
        registro.write_bytes(b"%PDF registro")
        return {
            "ruta_firmado": str(firmado),
            "ruta_registro_firma": str(registro),
            "sha256_firmado": "a" * 64,
            "sha256_registro_firma": "b" * 64,
        }


def test_tramites_dgt_schema(tmp_path: Path):
    gestor = GestorSQLite(tmp_path / "dgt.db")
    tables = _tables(gestor)
    assert "dgt_expedientes" in tables
    assert "dgt_documentos_generados" in tables
    assert "usuarios_permisos_globales" in tables
    for col in (
        "referencia", "estado", "vendedor_token_hash", "comprador_token_hash",
        "firma_provider", "codigo_tasa", "modelo_620_presentado",
    ):
        assert col in _columns(gestor, "dgt_expedientes")


def test_envia_ultimas_versiones_a_signrequest(tmp_path: Path):
    repo = _MemoryDgtRepository()
    expediente_id = "exp-firma"
    repo.expedientes[expediente_id] = {
        "id": expediente_id,
        "referencia": "DGT-2026-0099",
        "estado": "validado",
        "firma_estado": "",
        "vendedor_payload": {
            "email": "vendedor@example.com",
            "telefono": "+34600000001",
        },
        "comprador_payload": {
            "email": "comprador@example.com",
            "telefono": "+34600000002",
        },
    }
    for idx, tipo in enumerate(("contrato_compraventa", "mandato_dgt_comprador"), 1):
        path = tmp_path / f"{tipo}.pdf"
        path.write_bytes(b"%PDF-1.4")
        repo.insertar_documento_generado(
            {
                "expediente_id": expediente_id,
                "tipo_documento": tipo,
                "titulo": tipo,
                "ruta_pdf": str(path),
            }
        )
    firma = _FirmaClient()
    service = TramitesDgtService(repository=repo, firma_client=firma)

    result = service.enviar_a_firma(expediente_id, usar_sms=True)

    assert result["estado"] == "enviado"
    assert len(firma.envios[0]["firmantes"]) == 2
    assert len(firma.envios[1]["firmantes"]) == 1
    assert repo.expedientes[expediente_id]["firma_provider"] == "signrequest"
    assert service.actualizar_estado_firma(expediente_id)["estado"] == "firmado"
    assert len(repo.listar_documentos_generados(expediente_id)) == 6


def test_rechaza_contrato_con_el_mismo_email_para_ambas_partes(tmp_path: Path):
    repo = _MemoryDgtRepository()
    expediente_id = "exp-email-repetido"
    repo.expedientes[expediente_id] = {
        "id": expediente_id,
        "referencia": "DGT-2026-0100",
        "estado": "validado",
        "vendedor_payload": {"email": "misma@example.com"},
        "comprador_payload": {"email": "misma@example.com"},
    }
    path = tmp_path / "contrato.pdf"
    path.write_bytes(b"%PDF-1.4")
    repo.insertar_documento_generado(
        {
            "expediente_id": expediente_id,
            "tipo_documento": "contrato_compraventa",
            "ruta_pdf": str(path),
        }
    )
    service = TramitesDgtService(repository=repo, firma_client=_FirmaClient())

    try:
        service.enviar_a_firma(expediente_id)
    except ValueError as exc:
        assert "emails distintos" in str(exc)
    else:
        raise AssertionError("No debe enviar un contrato con un unico email para ambas partes")


def test_contexto_con_persona_juridica_no_duplica_rol_y_muestra_empresa_en_firma():
    service = TramitesDgtService(repository=_MemoryDgtRepository())
    comprador = {
        "tipo_persona": "juridica",
        "nombre": "Asesoria Gestinem, S.L.",
        "nif": "B12345674",
        "representante_nombre": "Juan Jose Dominguez",
        "representante_nif": "00000000T",
        "direccion": "Calle Mayor 1",
        "cp": "39001",
        "poblacion": "Santander",
        "provincia": "Cantabria",
        "telefono": "600000000",
        "email": "info@example.com",
    }

    comparecencia = service._comparecencia(comprador, "comprador")

    assert comparecencia.startswith("Asesoria Gestinem, S.L., con CIF")
    assert "la parte compradora" not in comparecencia
    assert service._firma_parte(comprador) == (
        "Asesoria Gestinem, S.L.\nD./Dña. Juan Jose Dominguez"
    )


def test_crear_validar_y_generar_documentos(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("services.tramites_dgt_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("services.tramites_dgt_service.get_word_templates_dir", lambda: str(tmp_path / "plantillas"))
    gestor = GestorSQLite(tmp_path / "dgt_service.db")
    service = TramitesDgtService(gestor)
    expediente_id = service.crear_expediente_minimo(
        {
            "vendedor_nombre": "Vendedor Demo",
            "comprador_nombre": "Comprador Demo",
            "vehiculo_matricula": "1234 ABC",
            "precio_venta": "1200,50",
        }
    )
    links = service.regenerar_links(expediente_id)
    vendedor_token = links["vendedor"].split("token=", 1)[1]
    expediente = service.get_expediente(expediente_id)
    assert expediente["referencia"].startswith("DGT-")
    assert expediente["vehiculo_matricula"] == "1234ABC"
    assert expediente["vendedor_token_hash"]
    assert expediente["comprador_token_hash"]

    service.completar_desde_link(
        expediente["referencia"],
        "vendedor",
        vendedor_token,
        {
            "nombre": "Vendedor Demo",
            "nif": "00000000T",
            "email": "vendedor@example.com",
            "telefono": "600000000",
            "direccion": "Calle Mayor 1",
            "cp": "39001",
            "poblacion": "Santander",
            "provincia": "Cantabria",
            "vehiculo_matricula": "1234 ABC",
            "vehiculo_bastidor": "WVWZZZ1JZXW000001",
            "vehiculo_marca": "Seat",
            "vehiculo_modelo": "Leon",
            "vehiculo_primera_matriculacion": "2020-01-15",
            "vehiculo_kilometros": "50000",
            "precio_venta": "1200,50",
            "fecha_operacion": "2026-07-24",
            "hora_entrega": "10:00",
            "forma_pago": "transferencia",
            "numero_llaves": "2",
        },
    )
    service.guardar_datos_parte(
        expediente_id,
        "comprador",
        {
            "nombre": "Comprador Demo",
            "nif": "00000001R",
            "email": "comprador@example.com",
            "telefono": "611111111",
            "direccion": "Calle Menor 2",
            "cp": "39002",
            "poblacion": "Santander",
            "provincia": "Cantabria",
            "envio_direccion": "Calle Menor 2",
            "envio_cp": "39002",
            "envio_poblacion": "Santander",
            "envio_provincia": "Cantabria",
        },
    )
    adjunto = tmp_path / "dni.pdf"
    adjunto.write_bytes(b"%PDF-1.4 demo")
    doc = service.adjuntar_documento(expediente_id, "comprador", str(adjunto), tipo="dni")
    assert doc["sha256"]

    service.validar_expediente(expediente_id)
    service.ensure_plantillas_editables()
    docs = service.generar_documentos(expediente_id)
    assert {doc["tipo_documento"] for doc in docs} == {
        "contrato_compraventa",
        "mandato_dgt_comprador",
    }
    for doc in docs:
        assert doc["fecha_generacion"]
        assert Path(doc["ruta_txt"]).exists()
        if doc.get("ruta_docx"):
            assert Path(doc["ruta_docx"]).exists()

    docs_regenerados = service.generar_documentos(expediente_id)
    assert {doc["ruta_txt"] for doc in docs}.isdisjoint(
        {doc["ruta_txt"] for doc in docs_regenerados}
    )
    service.eliminar_documento_generado(docs[0]["id"])
    assert Path(docs_regenerados[0]["ruta_txt"]).exists()

    paquete = service.preparar_paquete_firma(expediente_id, provider="box_sign")
    assert paquete["provider"] == "box_sign"
    assert len(paquete["documentos"]) == 2
    assert service.get_expediente(expediente_id)["firma_estado"] == "preparado"


def test_rechaza_token_dgt_incorrecto(tmp_path: Path):
    gestor = GestorSQLite(tmp_path / "dgt_token.db")
    service = TramitesDgtService(gestor)
    expediente_id = service.crear_expediente_minimo({"vendedor_nombre": "A", "comprador_nombre": "B"})
    expediente = service.get_expediente(expediente_id)
    try:
        service.verificar_token(expediente["referencia"], "vendedor", "token-malo")
    except PermissionError:
        pass
    else:
        raise AssertionError("El token incorrecto no fue rechazado")


def test_elimina_expediente_local_y_documentos_generados(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("services.tramites_dgt_service.get_app_data_dir", lambda: tmp_path)
    gestor = GestorSQLite(tmp_path / "dgt_delete.db")
    service = TramitesDgtService(gestor)
    expediente_id = service.crear_expediente_minimo({"vendedor_nombre": "Error"})
    expediente = service.get_expediente(expediente_id)
    output = service._output_dir(expediente)
    txt = output / "borrador.txt"
    txt.write_text("borrador", encoding="utf-8")
    doc_id = gestor.insertar_dgt_documento_generado(
        {
            "expediente_id": expediente_id,
            "tipo_documento": "borrador",
            "ruta_txt": str(txt),
        }
    )
    service.eliminar_documento_generado(doc_id)
    assert not txt.exists()
    assert service.listar_documentos(expediente_id) == []
    service.eliminar_expediente(expediente_id)
    assert service.get_expediente(expediente_id) is None


def test_parsea_link_seguro_y_completa_comprador(tmp_path: Path):
    gestor = GestorSQLite(tmp_path / "dgt_link.db")
    service = TramitesDgtService(gestor)
    expediente_id = service.crear_expediente_minimo({"vendedor_nombre": "A", "comprador_nombre": "B"})
    link = service.regenerar_links(expediente_id)["comprador"]
    parsed = service.parse_link_seguro(link)
    assert parsed["rol"] == "comprador"
    assert parsed["referencia"].startswith("DGT-")
    assert parsed["token"]

    service.completar_desde_link(
        parsed["referencia"],
        parsed["rol"],
        parsed["token"],
        {"nombre": "Comprador Link", "nif": "00000001R", "direccion": "Calle Link"},
    )
    expediente = service.get_expediente(expediente_id)
    assert expediente["comprador_nombre"] == "Comprador Link"
    assert expediente["comprador_payload"]["nif"] == "00000001R"


def test_plantillas_dgt_editables_en_carpeta_configurada(tmp_path: Path, monkeypatch):
    templates_dir = tmp_path / "plantillas_usuario"
    monkeypatch.setattr("services.tramites_dgt_service.get_word_templates_dir", lambda: str(templates_dir))
    gestor = GestorSQLite(tmp_path / "dgt_templates.db")
    service = TramitesDgtService(gestor)

    before = service.listar_plantillas_editables()
    assert all(str(templates_dir / "tramites_dgt") in item["path"] for item in before)
    assert not any(item["exists"] for item in before)

    created = service.ensure_plantillas_editables()
    assert len(created) == 2
    after = service.listar_plantillas_editables()
    assert all(item["exists"] for item in after)
    for item in after:
        assert Path(item["path"]).exists()


def test_detecta_url_protocolo_dgt_en_argv():
    url = "gest2a3eco://tramites-dgt/vendedor/DGT-2026-0001?token=abc"
    assert get_protocol_url_from_argv(["Gest2A3Eco.exe", url]) == url
    assert get_protocol_url_from_argv(["Gest2A3Eco.exe", "--otro"]) == ""


def test_permiso_global_tramites_dgt_en_usuario(tmp_path: Path):
    gestor = GestorSQLite(tmp_path / "dgt_perms.db")
    auth = AuthService(gestor)
    user_id = auth.save_user(
        user_id=None,
        username="empleado",
        nombre="Empleado",
        rol="empleado",
        activo=True,
        company_permissions={},
        global_permissions={"tramites_dgt"},
        password="secret",
    )
    rows = gestor.listar_permisos_globales_usuario(user_id)
    assert any(row["permiso"] == "tramites_dgt" and row["activo"] for row in rows)

    result = auth.authenticate("empleado", "secret")
    assert result.ok
    assert AuthorizationService(result.session).can_manage_tramites_dgt()

    auth.save_user(
        user_id=user_id,
        username="empleado",
        nombre="Empleado",
        rol="empleado",
        activo=True,
        company_permissions={},
        global_permissions=set(),
    )
    result = auth.authenticate("empleado", "secret")
    assert result.ok
    assert not AuthorizationService(result.session).can_manage_tramites_dgt()


def test_servicio_dgt_funciona_con_repositorio_no_sqlite():
    repo = _MemoryDgtRepository()
    service = TramitesDgtService(repository=repo)
    expediente_id = service.crear_expediente_minimo(
        {"vendedor_nombre": "A", "comprador_nombre": "B", "vehiculo_matricula": "1234ABC"}
    )
    assert service.get_expediente(expediente_id)["referencia"].startswith("DGT-")
    assert repo.expedientes[expediente_id]["estado"] == "borrador"


class _FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.content = b""
        self.response = self

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _FakeHttp:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "POST" and url.endswith("/links"):
            return _FakeResponse({
                "vendedor": {"url": "https://tramites.test/t/DGT-1/vendedor?token=v"},
                "comprador": {"url": "https://tramites.test/t/DGT-1/comprador?token=c"},
            })
        return _FakeResponse({})


def test_api_repository_delega_generacion_enlaces_https():
    http = _FakeHttp()
    repo = ApiDgtRepository("https://api.test", "secret", session=http)
    service = TramitesDgtService(repository=repo)
    links = service.regenerar_links("exp-1")
    assert links["vendedor"].startswith("https://")
    assert http.calls[0][2]["headers"]["X-API-Key"] == "secret"
