from __future__ import annotations

from io import BytesIO
from pathlib import Path
import shutil

from PIL import Image, UnidentifiedImageError

from utils.utilidades import get_document_repository_dir
from utils.validaciones import normalizar_codigo_empresa_a3


_FORMAT_SUFFIX = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}


def company_logos_dir() -> Path:
    """Directorio maestro compartido de logotipos empresariales."""
    path = get_document_repository_dir() / "assets" / "logos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validated_suffix(content: bytes) -> str:
    if not content:
        raise ValueError("El archivo de logotipo esta vacio.")
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            suffix = _FORMAT_SUFFIX.get(str(image.format or "").upper())
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("El logotipo no es una imagen valida.") from exc
    if not suffix:
        raise ValueError("El logotipo debe ser PNG, JPG o WEBP.")
    return suffix


def save_company_logo(company_code: str, content: bytes) -> Path:
    """Guarda atomicamente el logotipo en la ubicacion maestra compartida."""
    code = normalizar_codigo_empresa_a3(company_code)
    if not code:
        raise ValueError("El codigo de empresa es obligatorio para guardar el logotipo.")
    suffix = _validated_suffix(content)
    target = company_logos_dir() / f"{code}{suffix}"
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(target)
    for old_suffix in _FORMAT_SUFFIX.values():
        old_path = target.with_suffix(old_suffix)
        if old_path != target:
            old_path.unlink(missing_ok=True)
    return target


def delete_company_logo(company_code: str) -> bool:
    """Elimina las variantes maestras del logotipo de una empresa."""
    code = normalizar_codigo_empresa_a3(company_code)
    if not code:
        return False
    removed = False
    for suffix in _FORMAT_SUFFIX.values():
        path = company_logos_dir() / f"{code}{suffix}"
        if path.is_file():
            path.unlink()
            removed = True
    return removed


def import_company_logo(company_code: str, source: str | Path) -> Path:
    """Copia una imagen seleccionada por el usuario al repositorio maestro."""
    source_path = Path(source)
    if not source_path.is_file():
        raise ValueError(f"No se encuentra el archivo de logotipo: {source_path}")
    content = source_path.read_bytes()
    target = save_company_logo(company_code, content)
    if source_path.resolve() != target.resolve():
        try:
            shutil.copystat(source_path, target)
        except OSError:
            pass
    return target
