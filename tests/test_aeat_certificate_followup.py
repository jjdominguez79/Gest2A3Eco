"""Seguimiento AEAT sin presentar solicitudes ni acceder a la sede real."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.aapp.aeat_documentos import clasificar_texto, inspeccionar_pdf, referencia_solicitud
from services.aapp.base import OpcionesSync
from services.aapp.certificados import ResultadoCertificado, obtener_proveedor
from tests.test_aapp_worker import _Backend, _config
from tests.test_client_certificates_api import _setup
from aapp_worker.worker import AappWorker
from backend.api.client_models import ClientCertificateRequest, ClientDocument


@pytest.mark.parametrize("texto,clase,resultado", [
    ("RESGUARDO DE SOLICITUD DE EXPEDICION DE CERTIFICADO. Estar al corriente de obligaciones tributarias", "RESGUARDO", None),
    ("Justificante de presentación de la solicitud. Certificado tributario solicitado", "RESGUARDO", None),
    ("JUSTIFICANTE DE REGISTRO. Certificado tributario solicitado: positivo", "RESGUARDO", None),
    ("CERTIFICADO TRIBUTARIO. CERTIFICA: se encuentra al corriente de sus obligaciones tributarias", "CERTIFICADO", "POSITIVO"),
    ("CERTIFICADO TRIBUTARIO. CERTIFICA: NO se encuentra al corriente de sus obligaciones tributarias", "CERTIFICADO", "NEGATIVO"),
    ("CERTIFICADO TRIBUTARIO. Carácter: NEGATIVO", "CERTIFICADO", "NEGATIVO"),
    ("Solicitud de certificado al corriente", "REVISION", None),
    ("Documento escaneado sin texto", "REVISION", None),
    ("CERTIFICADO TRIBUTARIO. Situacion censal", "CERTIFICADO", None),
])
def test_clasificacion_no_confunde_resguardo_ni_titulo_con_resultado(texto, clase, resultado):
    doc = clasificar_texto(texto)
    assert (doc.clase, doc.resultado) == (clase, resultado)


def test_csv_no_es_referencia_y_referencias_ambiguas_no_se_eligen():
    assert referencia_solicitud("CSV: ABCDEFGHIJKLMNOP") is None
    assert referencia_solicitud("Referencia: 20260918AB1234") == "20260918AB1234"
    assert referencia_solicitud("Referencia: 20260918AB1234 Numero de expediente: 20260918XY5678") is None
    documento = clasificar_texto("RESGUARDO. Referencia: 20260918AB1234. Codigo Seguro de Verificacion: ABCDEFGHIJKLMNOP")
    assert documento.referencia == "20260918AB1234"
    assert documento.codigo_electronico == "ABCDEFGHIJKLMNOP"


def test_pdf_corrupto_requiere_revision(tmp_path):
    ruta = tmp_path / "corrupto.pdf"
    ruta.write_bytes(b"%PDF-1.7\nno es un PDF completo")
    assert inspeccionar_pdf(str(ruta)).clase == "REVISION"


def test_extraccion_pdf_usa_todas_las_paginas_sin_tocar_original(monkeypatch, tmp_path):
    import pypdf
    textos = ["CERTIFICADO TRIBUTARIO", "CERTIFICA: No se encuentra al corriente"]
    paginas = [SimpleNamespace(extract_text=lambda t=t: t) for t in textos]
    monkeypatch.setattr(pypdf, "PdfReader", lambda _ruta: SimpleNamespace(pages=paginas))
    ruta = tmp_path / "firmado.pdf"
    ruta.write_bytes(b"original firmado")
    assert inspeccionar_pdf(str(ruta)).resultado == "NEGATIVO"
    assert ruta.read_bytes() == b"original firmado"


class BackendSeguimiento(_Backend):
    def __init__(self, item):
        super().__init__(item)
        self.pending = None
        self.publicados = []

    def publish_pdf(self, item, path):
        self.publicados.append(item)
        return {"id": "resguardo-1"}

    def pending_issuance(self, item, **kwargs):
        self.pending = kwargs

    def receipt_pdf(self, item):
        return b"%PDF-1.7\noriginal"


def test_worker_archiva_resguardo_sin_completar(monkeypatch, tmp_path):
    item = {"id": "sol-1", "organization_id": "org-1", "certificate_type": "AEAT_CORRIENTE"}
    backend = BackendSeguimiento(item)

    class Proveedor:
        def obtener(self, cert, tipo, opciones):
            Path(opciones.ruta_pdf_destino).write_bytes(b"%PDF-1.7\nresguardo")
            return ResultadoCertificado(ok=False, tipo=tipo, estado="RESGUARDO",
                                        pdf_path=opciones.ruta_pdf_destino,
                                        referencia="20260918AB1234")

    monkeypatch.setattr("aapp_worker.worker.obtener_proveedor", lambda _tipo: Proveedor())
    AappWorker(_config(tmp_path), backend).run_once()
    assert backend.completed is None
    assert backend.failed is None
    assert backend.publicados[0]["_document_kind"] == "resguardo"
    assert backend.pending["receipt_document_id"] == "resguardo-1"
    assert backend.pending["reference"] == "20260918AB1234"
    assert backend.pending["requires_review"] is False


def test_worker_consulta_expediente_sin_republicar_resguardo(monkeypatch, tmp_path):
    from services.aapp.aeat_documentos import DocumentoAEAT
    monkeypatch.setattr("services.aapp.aeat_documentos.inspeccionar_pdf", lambda _ruta: DocumentoAEAT("RESGUARDO", referencia="20260918AB1234", codigo_electronico="ABCDEFGHIJKLMNOP"))
    item = {"id": "sol-1", "certificate_type": "AEAT_CORRIENTE", "submitted_at": "2026-09-18T18:00:00Z",
            "external_reference": "20260918AB1234", "receipt_document_id": "resguardo-1"}
    backend = BackendSeguimiento(item)

    class Proveedor:
        def obtener(self, cert, tipo, opciones):
            assert opciones.seguimiento_certificado == {"referencia": "20260918AB1234", "codigo_electronico": "ABCDEFGHIJKLMNOP"}
            return ResultadoCertificado(ok=False, tipo=tipo, estado="EN_TRAMITE", referencia="20260918AB1234")

    monkeypatch.setattr("aapp_worker.worker.obtener_proveedor", lambda _tipo: Proveedor())
    AappWorker(_config(tmp_path), backend).run_once()
    assert not backend.publicados
    assert backend.completed is None
    assert backend.pending["requires_review"] is False


def test_fallo_archivo_resguardo_no_representa_solicitud(monkeypatch, tmp_path):
    item = {"id": "sol-1", "certificate_type": "AEAT_CORRIENTE"}
    backend = BackendSeguimiento(item)
    backend.publish_pdf = lambda *_args: (_ for _ in ()).throw(RuntimeError("archivo indisponible"))

    class Proveedor:
        def obtener(self, cert, tipo, opciones):
            Path(opciones.ruta_pdf_destino).write_bytes(b"%PDF-1.7\nresguardo")
            return ResultadoCertificado(ok=False, tipo=tipo, estado="RESGUARDO",
                                        pdf_path=opciones.ruta_pdf_destino, referencia="20260918AB1234")

    monkeypatch.setattr("aapp_worker.worker.obtener_proveedor", lambda _tipo: Proveedor())
    AappWorker(_config(tmp_path), backend).run_once()
    assert backend.failed is None
    assert backend.pending["requires_review"] is True


def _expediente(monkeypatch):
    client, factory, org_id, headers = _setup(monkeypatch)
    created = client.post("/api/v1/messaging/client/certificates/requests", headers=headers,
                          json={"certificate_type": "AEAT_CORRIENTE", "idempotency_key": "expediente"}).json()
    with factory() as db:
        doc = ClientDocument(organization_id=org_id, document_type="resguardo_aeat", display_name="Resguardo",
                             file_name="resguardo.pdf", content_type="application/pdf", blob_key="resguardo.pdf",
                             sha256="a" * 64, source_system="aapp_worker", source_id=created["id"] + ":resguardo")
        db.add(doc)
        db.commit()
        receipt_id = doc.id
    claimed = client.post("/api/v1/messaging/client/certificates/internal/worker/claim").json()["item"]
    return client, factory, headers, claimed, receipt_id


def _pendiente(client, item, receipt_id=None, **kwargs):
    return client.post(
        f"/api/v1/messaging/client/certificates/internal/worker/requests/{item['id']}/pending-issuance",
        json={"claim_token": item["claim_token"], "receipt_document_id": receipt_id,
              "external_reference": "20260918AB1234", **kwargs},
    )


def test_programacion_24_48_72_horas_y_aviso_sin_resultado_negativo(monkeypatch):
    client, factory, headers, item, receipt_id = _expediente(monkeypatch)
    ahora = datetime(2026, 9, 18, 18, tzinfo=timezone.utc)
    monkeypatch.setattr("backend.api.client_certificates_api.utcnow", lambda: ahora)
    pendiente = _pendiente(client, item, receipt_id)
    assert pendiente.status_code == 200
    assert pendiente.json()["status"] == "awaiting_issuance"
    assert pendiente.json()["document_id"] is None
    assert pendiente.json()["receipt_document_id"] == receipt_id
    assert pendiente.json()["certificate_result"] is None
    assert client.post("/api/v1/messaging/client/certificates/internal/worker/claim").json()["item"] is None
    for horas in (24, 48, 72, 96):
        ahora = datetime(2026, 9, 18, 18, tzinfo=timezone.utc) + timedelta(hours=horas)
        claimed = client.post("/api/v1/messaging/client/certificates/internal/worker/claim").json()["item"]
        assert claimed["submitted_at"]
        assert claimed["external_reference"] == "20260918AB1234"
        respuesta = _pendiente(client, claimed)
        assert respuesta.status_code == 200
        assert respuesta.json()["status"] == "awaiting_issuance"
        assert respuesta.json()["certificate_result"] is None
        assert datetime.fromisoformat(respuesta.json()["next_attempt_at"]) == ahora + timedelta(hours=24)
        if horas >= 72:
            assert "72 horas" in respuesta.json()["error_message"]
    assert client.delete(f"/api/v1/messaging/client/certificates/requests/{item['id']}", headers=headers).status_code == 409
    assert client.post("/api/v1/messaging/client/certificates/requests", headers=headers,
                       json={"certificate_type": "AEAT_CORRIENTE", "idempotency_key": "duplicada"}).status_code == 409


@pytest.mark.parametrize("resultado", ["POSITIVO", "NEGATIVO"])
def test_certificado_definitivo_conserva_resguardo_y_resultado(monkeypatch, resultado):
    client, factory, headers, item, receipt_id = _expediente(monkeypatch)
    assert _pendiente(client, item, receipt_id).status_code == 200
    assert client.post(f"/api/v1/messaging/client/certificates/requests/{item['id']}/retry", headers=headers).status_code == 200
    claimed = client.post("/api/v1/messaging/client/certificates/internal/worker/claim").json()["item"]
    with factory() as db:
        doc = ClientDocument(organization_id=claimed["organization_id"], document_type="certificado_aeat",
                             display_name="Certificado", file_name="certificado.pdf", blob_key="certificado.pdf",
                             sha256="b" * 64, source_system="aapp_worker", source_id=item["id"])
        db.add(doc)
        db.commit()
        certificate_id = doc.id
    resultado_final = client.post(
        f"/api/v1/messaging/client/certificates/internal/worker/requests/{item['id']}/complete",
        json={"claim_token": claimed["claim_token"], "document_id": certificate_id,
              "result_summary": resultado, "certificate_result": resultado},
    )
    assert resultado_final.status_code == 200
    assert resultado_final.json()["status"] == "completed"
    assert resultado_final.json()["certificate_result"] == resultado
    assert resultado_final.json()["receipt_document_id"] == receipt_id
    assert resultado_final.json()["document_id"] == certificate_id
    with factory() as db:
        assert db.get(ClientDocument, receipt_id) is not None


def test_referencia_no_identificada_reintenta_consulta_nunca_presentacion(monkeypatch):
    client, factory, headers, item, receipt_id = _expediente(monkeypatch)
    respuesta = _pendiente(client, item, receipt_id, external_reference="")
    assert respuesta.json()["status"] == "needs_action"
    assert respuesta.json()["next_attempt_at"] is None
    reintento = client.post(f"/api/v1/messaging/client/certificates/requests/{item['id']}/retry", headers=headers)
    assert reintento.json()["status"] == "awaiting_issuance"
    assert reintento.json()["receipt_document_id"] == receipt_id
    assert reintento.json()["submitted_at"]


def test_otro_documento_o_referencia_no_se_adopta(monkeypatch):
    client, factory, headers, item, receipt_id = _expediente(monkeypatch)
    assert _pendiente(client, item, "documento-inexistente").status_code == 422
    assert _pendiente(client, item, receipt_id).status_code == 200
    client.post(f"/api/v1/messaging/client/certificates/requests/{item['id']}/retry", headers=headers)
    claimed = client.post("/api/v1/messaging/client/certificates/internal/worker/claim").json()["item"]
    assert _pendiente(client, claimed, external_reference="OTRO123456").status_code == 409


def test_resguardo_no_puede_marcarse_como_certificado_definitivo(monkeypatch):
    client, factory, headers, item, receipt_id = _expediente(monkeypatch)
    assert _pendiente(client, item, receipt_id).status_code == 200
    client.post(f"/api/v1/messaging/client/certificates/requests/{item['id']}/retry", headers=headers)
    claimed = client.post("/api/v1/messaging/client/certificates/internal/worker/claim").json()["item"]
    respuesta = client.post(
        f"/api/v1/messaging/client/certificates/internal/worker/requests/{item['id']}/complete",
        json={"claim_token": claimed["claim_token"], "document_id": receipt_id,
              "certificate_result": "POSITIVO"},
    )
    assert respuesta.status_code == 422


def test_consulta_sin_referencia_no_interactua_con_formularios():
    class Pagina:
        def __getattr__(self, nombre):
            raise AssertionError("No se debe interactuar sin referencia")
    resultado = obtener_proveedor("AEAT_CORRIENTE")._aeat_consultar_solicitud(
        Pagina(), OpcionesSync(seguimiento_certificado={"referencia": ""}), "AEAT_CORRIENTE",
    )
    assert resultado.estado == "PENDIENTE"
    assert not resultado.ok


def test_tramite_sin_recogida_configurada_no_abre_certificado_ni_presenta():
    resultado = obtener_proveedor("AEAT_CONTRATISTAS").obtener(
        None, "AEAT_CONTRATISTAS",
        OpcionesSync(seguimiento_certificado={"referencia": "20260918AB1234"}),
    )
    assert resultado.estado == "PENDIENTE"
    assert not resultado.ok


def test_contratistas_rellena_solo_cif_si_no_hay_razon_social():
    rellenados = {}

    class Control:
        def __init__(self, campo):
            self.campo = campo

        def count(self):
            return 1

        @property
        def first(self):
            return self

        def fill(self, value, timeout):
            rellenados[self.campo] = (value, timeout)

    class Pagina:
        def locator(self, selector):
            return Control("cif") if "nif" in selector.lower() else Control("razon_social")

    proveedor = obtener_proveedor("AEAT_CONTRATISTAS")
    assert proveedor._aeat_rellenar_contratante(
        Pagina(),
        OpcionesSync(parametros={"contracting_party_tax_id": "B12345678"}),
    )
    assert rellenados == {"cif": ("B12345678", 5000)}


def test_worker_no_consulta_con_resguardo_de_otro_expediente(monkeypatch, tmp_path):
    from services.aapp.aeat_documentos import DocumentoAEAT
    backend = BackendSeguimiento({"id": "sol-1", "certificate_type": "AEAT_CORRIENTE", "submitted_at": "2026-09-18",
                                  "receipt_document_id": "resguardo-1", "external_reference": "20260918AB1234"})
    monkeypatch.setattr("services.aapp.aeat_documentos.inspeccionar_pdf", lambda _ruta: DocumentoAEAT("RESGUARDO", referencia="20260918ZZ9999"))
    class Proveedor:
        def obtener(self, *_args):
            pytest.fail("No debe abrir la sede con otro resguardo")
    monkeypatch.setattr("aapp_worker.worker.obtener_proveedor", lambda _tipo: Proveedor())
    AappWorker(_config(tmp_path), backend).run_once()
    assert backend.failed is not None
    assert backend.completed is None
    assert not backend.publicados


def test_reclasifica_resguardo_historico_conservando_pdf_y_no_hace_solicitud(monkeypatch):
    client, factory, headers, item, receipt_id = _expediente(monkeypatch)
    with factory() as db:
        solicitud = db.get(ClientCertificateRequest, item["id"])
        solicitud.status = "completed"
        solicitud.document_id = receipt_id
        solicitud.completed_at = datetime(2026, 9, 18, 14, tzinfo=timezone.utc)
        solicitud.result_summary = "POSITIVO"  # Inferencia antigua, incorrecta.
        documento = db.get(ClientDocument, receipt_id)
        documento.source_id = item["id"]
        documento.document_type = "certificado_aeat"
        db.commit()
    url = f"/api/v1/messaging/client/certificates/internal/requests/{item['id']}/reclassify-receipt"
    payload = {"document_id": receipt_id, "expected_sha256": "a" * 64,
               "external_reference": "20260918AB1234"}
    assert client.post(url, params={"company_code": "E00001"}, json={**payload, "expected_sha256": "b" * 64}).status_code == 409
    respuesta = client.post(url, params={"company_code": "E00001"}, json=payload)
    assert respuesta.status_code == 200
    assert respuesta.json()["status"] == "awaiting_issuance"
    assert respuesta.json()["document_id"] is None
    assert respuesta.json()["receipt_document_id"] == receipt_id
    assert respuesta.json()["certificate_result"] is None
    assert "2026-09-18T14:00:00" in respuesta.json()["submitted_at"]
    assert client.post(url, params={"company_code": "E00001"}, json=payload).status_code == 200
    with factory() as db:
        documento = db.get(ClientDocument, receipt_id)
        assert documento.blob_key == "resguardo.pdf"
        assert documento.sha256 == "a" * 64
        assert documento.source_id == item["id"] + ":resguardo"
        assert documento.document_type == "resguardo_aeat"


@pytest.mark.parametrize("modo", ["pendiente", "formulario_real", "ficha_pendiente", "ficha_certificado", "ficha_ajena", "ficha_codigo", "ficha_codigo_ajeno", "ficha_codigo_certificado", "certificado", "otro_expediente", "ambiguo", "externo", "sin_enlace"])
def test_recogida_con_dom_real_nunca_presenta_y_no_mezcla_expedientes(monkeypatch, tmp_path, modo):
    from playwright.sync_api import sync_playwright
    from services.aapp.aeat_documentos import DocumentoAEAT
    import services.aapp.aeat_documentos as documentos
    referencia = "20260918AB1234"
    otra = "20260918ZZ9999"
    texto = "En tramitacion" if modo in {"pendiente", "formulario_real"} else "Emitido"
    href = "https://www1.agenciatributaria.gob.es/documento.pdf"
    if modo == "externo":
        href = "https://otro.example.test/documento.pdf"
    enlace = f'<a href="{href}">Certificado tributario</a>' if modo not in {"pendiente", "formulario_real", "sin_enlace"} else ""
    fila = f"<tr><td>{otra if modo == 'otro_expediente' else referencia}</td><td>{texto}</td><td>{enlace}</td></tr>"
    contenido = "<table>" + fila + (fila if modo == "ambiguo" else "") + "</table>"
    # Si se intentara firmar o validar, se detectaria como interaccion ajena.
    contenido += '<button id="validarSolicitud" onclick="window.presentadas++">Validar solicitud</button><script>window.presentadas=0;</script>'
    if modo == "formulario_real" or modo.startswith("ficha_"):
        contenido += ('<form onsubmit="event.preventDefault(); window.consultadas++">'
                      '<input type="radio" id="fRepresenta0" name="fRepresenta">'
                      '<label for="fCodSolicitud">Codigo de solicitud</label>'
                      '<input id="fCodSolicitud" name="fCodSolicitud">'
                      '<input type="date" id="fFecSolDesde" value="2026-09-18">'
                      '<input type="date" id="fFecSolHasta" value="2026-09-18">'
                      '<input type="submit" id="Enviar" value="Enviar">'
                      '</form><script>window.consultadas=0;</script>')
        if modo.startswith("ficha_"):
            import json
            ficha = f'<p>Referencia: {otra if modo == "ficha_ajena" else referencia}</p>'
            ficha += '<p>En tramitacion</p>' if modo == "ficha_pendiente" else f'<a href="{href}">Pinche aqui para recoger el certificado</a>'
            if modo.startswith("ficha_codigo"):
                codigo_ficha = "QRSTUVWXYZABCDEF" if modo == "ficha_codigo_ajeno" else "ABCDEFGHIJKLMNOP"
                ficha = f'<p>Codigo electronico de la solicitud: {codigo_ficha}</p>'
                ficha += (f'<a href="{href}">Pinche aqui para recoger el certificado</a>'
                          if modo == "ficha_codigo_certificado" else '<p>Estado de tramitacion: Solicitado</p>')
            ficha += '<footer><a href="https://www1.agenciatributaria.gob.es/certificado-sede">Validacion del certificado de sede</a></footer>'
            contenido += '<script>document.querySelector("form").onsubmit=function(e){e.preventDefault(); document.body.innerHTML=' + json.dumps(ficha) + ';};</script>'
    descargados = []
    provider = obtener_proveedor("AEAT_CORRIENTE")
    monkeypatch.setattr(provider, "_pdf_bytes_request", lambda _page, url, _options: descargados.append(url) or b"%PDF-1.7\nprueba")
    monkeypatch.setattr(documentos, "inspeccionar_pdf", lambda _ruta: DocumentoAEAT("CERTIFICADO", "NEGATIVO", referencia))
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=True)
        pagina = navegador.new_page()
        pagina.set_content(contenido)
        resultado = provider._aeat_consultar_solicitud(
            pagina, OpcionesSync(ruta_pdf_destino=str(tmp_path / "certificado.pdf"),
                                seguimiento_certificado={"referencia": referencia, "codigo_electronico": "ABCDEFGHIJKLMNOP"}), "AEAT_CORRIENTE",
        )
        assert pagina.evaluate("window.presentadas") == 0
        if modo == "formulario_real":
            assert pagina.evaluate("window.consultadas") == 1
            assert pagina.locator("#fCodSolicitud").input_value() == "ABCDEFGHIJKLMNOP"
            assert pagina.locator("#fFecSolDesde").input_value() == ""
            assert pagina.locator("#fRepresenta0").is_checked()
        navegador.close()
    if modo in {"certificado", "ficha_certificado", "ficha_codigo_certificado"}:
        assert resultado.estado == "OBTENIDO"
        assert resultado.resultado == "NEGATIVO"
        assert descargados == [href]
    else:
        assert not descargados
        assert not resultado.ok
        assert resultado.estado == ("EN_TRAMITE" if modo in {"pendiente", "formulario_real", "ficha_pendiente", "ficha_codigo"} else "PENDIENTE")


def test_resguardo_worker_exige_claim_y_documento_del_expediente(monkeypatch):
    client, factory, headers, item, receipt_id = _expediente(monkeypatch)
    _pendiente(client, item, receipt_id)
    client.post(f"/api/v1/messaging/client/certificates/requests/{item['id']}/retry", headers=headers)
    claimed = client.post("/api/v1/messaging/client/certificates/internal/worker/claim").json()["item"]
    url = "/api/v1/messaging/client/certificates/internal/worker/receipt-document"
    payload = {"request_id": item["id"], "claim_token": claimed["claim_token"]}
    assert client.post(url, json={**payload, "claim_token": "0" * 48}).status_code == 409
    monkeypatch.setattr("backend.api.client_certificates_api.ClientDocumentStorage", lambda: SimpleNamespace(get=lambda clave: b"%PDF-original" if clave == "resguardo.pdf" else pytest.fail("Documento ajeno")))
    assert client.post(url, json=payload).content == b"%PDF-original"
