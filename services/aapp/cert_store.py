"""
Almacen / cargador de certificados digitales de clientes (modelo de certificado
unico: cada cliente/empresa tiene UN solo certificado).

Responsabilidades:
  - Resolver, a partir de un buzon o de una empresa, el certificado del cliente
    y su ruta + contrasena descifrada.
  - Validar el fichero PFX/P12 (que la ruta existe y la contrasena es correcta).
  - Extraer metadatos utiles del certificado (NIF del titular, caducidad) para
    autocompletar la ficha y avisar de certificados caducados.

Los conectores (Playwright) usan directamente la RUTA del .pfx + la contrasena;
por eso CertMaterial expone ambos, ademas del objeto ya parseado si se necesita.

Requiere la libreria 'cryptography'. Si no esta instalada, la validacion/lectura
de metadatos se degrada con un mensaje claro, pero la ruta + contrasena siguen
disponibles para el conector.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from utils.crypto_utils import descifrar_password

try:
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    _CRYPTO_OK = True
except Exception:  # pragma: no cover - depende del entorno
    _CRYPTO_OK = False


@dataclass
class CertMaterial:
    cert_id: str
    nombre: str
    nif_titular: str | None
    ruta_archivo: str
    password: str | None
    fecha_caducidad: str | None = None
    _cert_obj: object | None = None

    @property
    def existe(self) -> bool:
        return bool(self.ruta_archivo) and os.path.isfile(self.ruta_archivo)


class CertError(Exception):
    pass


class CertStore:
    def __init__(self, gestor):
        self._gestor = gestor

    # ── resolucion desde buzon / empresa / certificado ───────────────────
    def material_para_empresa(self, codigo_empresa: str) -> CertMaterial:
        """Devuelve el UNICO certificado del cliente (modelo de certificado unico)."""
        certs = self._gestor.listar_notif_certificados(codigo_empresa, solo_activos=True)
        if not certs:
            certs = self._gestor.listar_notif_certificados(codigo_empresa)
        if not certs:
            raise CertError(
                f"El cliente {codigo_empresa} no tiene certificado digital configurado. "
                "Configuralo en la pestana 'Certificado' del cliente."
            )
        return self.material_para_certificado(certs[0]["id"])

    def material_para_buzon(self, buzon: dict) -> CertMaterial:
        # Modelo de certificado unico: se usa el certificado del cliente.
        # Se respeta certificado_id solo si apunta a un certificado existente.
        cert_id = buzon.get("certificado_id")
        if cert_id and self._gestor.get_notif_certificado(cert_id):
            return self.material_para_certificado(cert_id)
        return self.material_para_empresa(buzon.get("codigo_empresa"))

    def material_para_certificado(self, cert_id: str) -> CertMaterial:
        cert = self._gestor.get_notif_certificado(cert_id)
        if not cert:
            raise CertError(f"Certificado {cert_id} no encontrado.")
        ruta = cert.get("ruta_archivo") or ""
        password = descifrar_password(cert.get("password_cifrada"))
        mat = CertMaterial(
            cert_id=cert_id,
            nombre=cert.get("nombre", ""),
            nif_titular=cert.get("nif_titular"),
            ruta_archivo=ruta,
            password=password,
            fecha_caducidad=cert.get("fecha_caducidad"),
        )
        if not mat.existe:
            raise CertError(
                f"No se encuentra el fichero del certificado '{mat.nombre}':\n{ruta or '(ruta vacia)'}"
            )
        return mat

    # ── validacion / metadatos ───────────────────────────────────────────
    def validar(self, mat: CertMaterial) -> tuple[bool, str]:
        if not mat.existe:
            return False, f"No existe el fichero: {mat.ruta_archivo}"
        if not _CRYPTO_OK:
            return True, "Fichero presente (validacion completa requiere 'cryptography')."
        try:
            self._parse(mat)
        except Exception as exc:
            return False, f"No se pudo abrir el certificado (contrasena incorrecta o fichero danado): {exc}"
        vencido = self._esta_caducado(mat)
        if vencido is True:
            return False, f"El certificado esta CADUCADO (caducidad {mat.fecha_caducidad})."
        return True, "Certificado valido."

    def info(self, mat: CertMaterial) -> dict:
        if not _CRYPTO_OK:
            raise CertError("Falta la libreria 'cryptography' para leer el certificado.")
        cert = self._parse(mat)
        return _extraer_info(cert)

    def actualizar_caducidad_en_ficha(self, mat: CertMaterial) -> str | None:
        try:
            data = self.info(mat)
        except Exception:
            return None
        cad = data.get("fecha_caducidad")
        if cad:
            fila = self._gestor.get_notif_certificado(mat.cert_id) or {}
            fila["id"] = mat.cert_id
            fila["fecha_caducidad"] = cad
            if data.get("nif") and not fila.get("nif_titular"):
                fila["nif_titular"] = data["nif"]
            if data.get("fecha_emision") and not fila.get("fecha_emision"):
                fila["fecha_emision"] = data["fecha_emision"]
            self._gestor.upsert_notif_certificado(fila)
        return cad

    # ── interno ──────────────────────────────────────────────────────────
    def _parse(self, mat: CertMaterial):
        if mat._cert_obj is not None:
            return mat._cert_obj
        with open(mat.ruta_archivo, "rb") as fh:
            data = fh.read()
        pwd = mat.password.encode("utf-8") if mat.password else None
        _key, cert, _add = pkcs12.load_key_and_certificates(data, pwd)
        if cert is None:
            raise CertError("El PFX no contiene certificado de titular.")
        mat._cert_obj = cert
        return cert

    def _esta_caducado(self, mat: CertMaterial):
        try:
            cert = self._parse(mat)
            not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
            if not_after.tzinfo is None:
                not_after = not_after.replace(tzinfo=timezone.utc)
            mat.fecha_caducidad = not_after.date().isoformat()
            return datetime.now(timezone.utc) > not_after
        except Exception:
            return None


def _extraer_info(cert) -> dict:
    def _cn(name):
        try:
            attrs = name.get_attributes_for_oid(NameOID.COMMON_NAME)
            return attrs[0].value if attrs else None
        except Exception:
            return None

    def _serial_nif(cert):
        try:
            attrs = cert.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
            if attrs:
                val = attrs[0].value
                return val.replace("IDCES-", "").replace("IDCit-", "").strip() or None
        except Exception:
            pass
        cn = _cn(cert.subject) or ""
        import re
        m = re.search(r"\b([0-9A-Z]{8,10}[A-Z]?)\b", cn.replace("NIF", " "))
        return m.group(1) if m else None

    not_before = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before
    not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
    return {
        "cn": _cn(cert.subject),
        "nif": _serial_nif(cert),
        "fecha_emision": not_before.date().isoformat(),
        "fecha_caducidad": not_after.date().isoformat(),
    }
