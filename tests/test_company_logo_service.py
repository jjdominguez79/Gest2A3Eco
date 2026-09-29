from io import BytesIO

from PIL import Image

from services.company_logo_service import (
    delete_company_logo,
    import_company_logo,
    save_company_logo,
)


def _image_bytes(image_format: str = "PNG") -> bytes:
    stream = BytesIO()
    Image.new("RGB", (20, 10), "navy").save(stream, format=image_format)
    return stream.getvalue()


def test_guarda_logo_en_assets_compartidos_con_codigo_normalizado(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "services.company_logo_service.get_document_repository_dir",
        lambda: tmp_path,
    )

    target = save_company_logo("e00578", _image_bytes())

    assert target == tmp_path / "assets" / "logos" / "E00578.png"
    assert target.is_file()


def test_importa_logo_jpeg_a_la_ubicacion_maestra(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "services.company_logo_service.get_document_repository_dir",
        lambda: tmp_path / "repositorio",
    )
    source = tmp_path / "marca.dat"
    source.write_bytes(_image_bytes("JPEG"))

    target = import_company_logo("E00006", source)

    assert target.name == "E00006.jpg"
    assert target.read_bytes() == source.read_bytes()


def test_sustituir_formato_elimina_la_variante_anterior(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "services.company_logo_service.get_document_repository_dir",
        lambda: tmp_path,
    )
    old = save_company_logo("E00006", _image_bytes("PNG"))
    current = save_company_logo("E00006", _image_bytes("JPEG"))

    assert not old.exists()
    assert current.name == "E00006.jpg"


def test_elimina_todas_las_variantes_del_logo(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "services.company_logo_service.get_document_repository_dir",
        lambda: tmp_path,
    )
    logos = tmp_path / "assets" / "logos"
    logos.mkdir(parents=True)
    for suffix in (".png", ".jpg", ".webp"):
        (logos / f"E00006{suffix}").write_bytes(b"old")

    assert delete_company_logo("E00006") is True
    assert not list(logos.glob("E00006.*"))
