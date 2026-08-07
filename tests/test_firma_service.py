from pathlib import Path

import pytest
from pypdf import PdfWriter

from models.gestor_sqlite import GestorSQLite
from services.firma.firma_service import FirmaService


class FakeProvider:
    def __init__(self):
        self.envios = []

    def enviar_documento(self, ruta, firmantes, asunto, mensaje, external_id,
                         callback_url="", usar_sms=False):
        self.envios.append({"ruta": ruta, "firmantes": firmantes})
        return {"uuid": "firma-1", "status": "sent"}

    def consultar(self, request_id):
        return {"status": "signed"}

    def cancelar(self, request_id):
        return {"cancelled": True}

    def reenviar(self, request_id):
        return {"resent": True}

    def descargar_evidencias(self, request_id, destino, nombre_base):
        base = Path(destino)
        base.mkdir(parents=True, exist_ok=True)
        firmado = base / f"{nombre_base}_firmado.pdf"
        registro = base / f"{nombre_base}_registro_firma.pdf"
        firmado.write_bytes(b"firmado")
        registro.write_bytes(b"registro")
        return {"ruta_firmado": str(firmado), "ruta_registro_firma": str(registro),
                "sha256_firmado": "a" * 64, "sha256_registro_firma": "b" * 64}


def _pdf(path):
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    with path.open("wb") as fh:
        writer.write(fh)


def _service(tmp_path):
    gestor = GestorSQLite(tmp_path / "firma.db")
    pdf = tmp_path / "contrato.pdf"
    _pdf(pdf)
    provider = FakeProvider()
    return gestor, pdf, provider, FirmaService(gestor, provider=provider)


def test_permite_firmantes_externos_y_el_remitente_en_indice_cero(tmp_path):
    gestor, pdf, provider, service = _service(tmp_path)
    solicitud = service.crear_solicitud(
        "E00001", 2026, str(pdf), [
            {"orden": 1, "nombre": "Gestor", "email": "gestor@example.com", "es_remitente": True},
            {"orden": 2, "nombre": "Proveedor", "email": "externo@example.com"},
        ], zonas=[{"pagina": 0, "x": .1, "y": .2, "ancho": .3, "alto": .1, "firmante": 1}],
    )
    service.enviar(solicitud)
    assert provider.envios[0]["firmantes"][1]["email"] == "externo@example.com"
    import fitz
    pdf_preparado = fitz.open(provider.envios[0]["ruta"])
    assert "[[s|1]]" in pdf_preparado[0].get_text()
    pdf_preparado.close()
    gestor.conn.close()


@pytest.mark.parametrize("firmantes,mensaje", [
    ([{"orden": 1, "email": "uno@example.com"}, {"orden": 2, "email": "uno@example.com"}], "duplicados"),
    ([{"orden": 1, "email": "sin-formato"}], "valido"),
])
def test_valida_firmantes(tmp_path, firmantes, mensaje):
    gestor, pdf, _provider, service = _service(tmp_path)
    with pytest.raises(ValueError):
        service.crear_solicitud("E00001", 2026, str(pdf), firmantes)
    gestor.conn.close()


def test_actualizar_descarga_evidencias_y_guarda_estado(tmp_path):
    gestor, pdf, provider, service = _service(tmp_path)
    solicitud = service.crear_solicitud(
        "E00001", 2026, str(pdf), [{"orden": 1, "email": "externo@example.com"}],
    )
    service.enviar(solicitud)
    estado = service.actualizar_estado(solicitud, str(tmp_path / "evidencias"))
    assert estado["estado"] == "firmado"
    assert Path(estado["ruta_firmado"]).exists()
    assert provider.envios
    gestor.conn.close()


def test_firma_global_y_categoria_firmas_existen(tmp_path):
    gestor = GestorSQLite(tmp_path / "global.db")
    categorias = {item["id"] for item in gestor.listar_categorias_documentales()}
    assert "firmas" in categorias
    gestor.crear_firma_solicitud(
        {"id": "global-1", "codigo_empresa": "__GLOBAL__", "ejercicio": 2026,
         "nombre_documento": "libre.pdf", "ruta_origen": "C:/libre.pdf",
         "hash_origen": "a" * 64},
        [{"orden": 1, "email": "externo@example.com"}], [],
    )
    assert gestor.listar_todas_firma_solicitudes()[0]["codigo_empresa"] == "__GLOBAL__"
    gestor.conn.close()


def test_puede_marcar_pendiente_reenviar_y_finalizar(tmp_path):
    gestor, pdf, provider, service = _service(tmp_path)
    solicitud = service.crear_solicitud(
        "__GLOBAL__", 2026, str(pdf), [{"orden": 1, "email": "externo@example.com"}],
    )
    service.enviar(solicitud)
    service.finalizar(solicitud)
    assert gestor.get_firma_solicitud(solicitud)["estado"] == "finalizado"
    service.marcar_pendiente(solicitud)
    assert gestor.get_firma_solicitud(solicitud)["estado"] == "borrador"
    service.reenviar(solicitud)
    assert len(provider.envios) == 2
    gestor.conn.close()
