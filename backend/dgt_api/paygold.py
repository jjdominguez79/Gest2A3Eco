from __future__ import annotations

import base64
import hashlib
import hmac
import json
from decimal import Decimal, ROUND_HALF_UP

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, modes

try:
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
except ImportError:  # cryptography anterior a 43
    from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES


SIGNATURE_VERSION = "HMAC_SHA256_V1"
ERROR_MESSAGES = {
    "SIS0324": "No se pudo enviar el enlace al titular.",
    "SIS0325": "El enlace PayGold ya finalizo o no existe.",
    "SIS0487": "El comercio o terminal no tiene PayGold habilitado.",
}


def importe_centimos(importe: Decimal | str | float) -> str:
    value = Decimal(str(importe)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if value <= 0:
        raise ValueError("El importe debe ser mayor que cero.")
    return str(int(value * 100))


def codificar_parametros(parameters: dict) -> str:
    raw = json.dumps(parameters, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def decodificar_parametros(encoded: str) -> dict:
    padding = "=" * (-len(encoded) % 4)
    raw = base64.urlsafe_b64decode((encoded + padding).encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def firmar_parametros(secret_key: str, order: str, merchant_parameters: str) -> str:
    key = base64.b64decode(str(secret_key).strip())
    order_bytes = str(order).encode("utf-8")
    order_bytes += b"\0" * (-len(order_bytes) % 8)
    encryptor = Cipher(TripleDES(key), modes.CBC(b"\0" * 8)).encryptor()
    operation_key = encryptor.update(order_bytes) + encryptor.finalize()
    digest = hmac.new(
        operation_key,
        merchant_parameters.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def firmas_coinciden(received: str, expected: str) -> bool:
    def normalized(value: str) -> bytes:
        value = str(value or "").strip().replace(" ", "+")
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))

    try:
        return hmac.compare_digest(normalized(received), normalized(expected))
    except Exception:
        return False


class PayGoldClient:
    def __init__(
        self,
        merchant_code: str,
        terminal: str,
        secret_key: str,
        endpoint: str,
        notification_url: str,
        timeout: int = 50,
        session=None,
    ):
        self.merchant_code = str(merchant_code or "").strip()
        self.terminal = str(terminal or "").strip()
        self.secret_key = str(secret_key or "").strip()
        self.endpoint = str(endpoint or "").strip()
        self.notification_url = str(notification_url or "").strip()
        self.timeout = int(timeout)
        self._http = session or requests.Session()
        if not all((self.merchant_code, self.terminal, self.secret_key, self.endpoint)):
            raise ValueError("La configuracion PayGold esta incompleta.")

    def crear_enlace(
        self,
        *,
        order: str,
        amount_cents: str,
        description: str,
        customer_name: str,
        expiry_minutes: int,
        customer_email: str = "",
        customer_mobile: str = "",
        enviar_desde_redsys: bool = False,
    ) -> dict:
        parameters = {
            "DS_MERCHANT_ORDER": order,
            "DS_MERCHANT_MERCHANTCODE": self.merchant_code,
            "DS_MERCHANT_TERMINAL": self.terminal,
            "DS_MERCHANT_CURRENCY": "978",
            "DS_MERCHANT_TRANSACTIONTYPE": "F",
            "DS_MERCHANT_AMOUNT": amount_cents,
            "DS_MERCHANT_PRODUCTDESCRIPTION": description[:125],
            "DS_MERCHANT_P2F_EXPIRYDATE": str(expiry_minutes),
        }
        if self.notification_url:
            parameters["DS_MERCHANT_MERCHANTURL"] = self.notification_url
        if customer_name:
            parameters["DS_MERCHANT_TITULAR"] = customer_name[:60]
        if enviar_desde_redsys:
            if customer_email:
                parameters["DS_MERCHANT_CUSTOMER_MAIL"] = customer_email
            if customer_mobile:
                parameters["DS_MERCHANT_CUSTOMER_MOBILE"] = customer_mobile

        encoded = codificar_parametros(parameters)
        payload = {
            "Ds_SignatureVersion": SIGNATURE_VERSION,
            "Ds_MerchantParameters": encoded,
            "Ds_Signature": firmar_parametros(self.secret_key, order, encoded),
        }
        response = self._http.post(self.endpoint, json=payload, timeout=self.timeout)
        if response.status_code >= 400:
            raise RuntimeError(f"Redsys no respondio correctamente ({response.status_code}).")
        data = response.json()
        if data.get("errorCode"):
            code = str(data["errorCode"])
            detail = ERROR_MESSAGES.get(code, "Redsys rechazo la solicitud.")
            raise ValueError(f"{detail} ({code})")
        return self.validar_respuesta(data)

    def validar_respuesta(self, envelope: dict) -> dict:
        encoded = str(
            envelope.get("Ds_MerchantParameters")
            or envelope.get("DS_MERCHANTPARAMETERS")
            or ""
        )
        signature = str(
            envelope.get("Ds_Signature") or envelope.get("DS_SIGNATURE") or ""
        )
        if not encoded or not signature:
            raise ValueError("La respuesta de Redsys no contiene firma ni parametros.")
        parameters = decodificar_parametros(encoded)
        order = str(parameters.get("Ds_Order") or parameters.get("DS_ORDER") or "")
        expected = firmar_parametros(self.secret_key, order, encoded)
        if not order or not firmas_coinciden(signature, expected):
            raise ValueError("La firma de la respuesta de Redsys no es valida.")
        return parameters
