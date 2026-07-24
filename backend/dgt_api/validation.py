from __future__ import annotations

import re
from datetime import date

from backend.dgt_api.models import Parte

_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_CIF_CONTROL = "JABCDEFGHI"


def normalizar_identificacion(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def validar_nif(value: str) -> bool:
    nif = normalizar_identificacion(value)
    if re.fullmatch(r"\d{8}[A-Z]", nif):
        return _DNI_LETTERS[int(nif[:8]) % 23] == nif[8]
    if re.fullmatch(r"[XYZ]\d{7}[A-Z]", nif):
        return validar_nif({"X": "0", "Y": "1", "Z": "2"}[nif[0]] + nif[1:])
    if not re.fullmatch(r"[A-Z]\d{7}[0-9A-J]", nif):
        return False
    digits = nif[1:8]
    even = sum(int(digits[index]) for index in (1, 3, 5))
    odd = sum(divmod(int(digits[index]) * 2, 10)[0] + divmod(int(digits[index]) * 2, 10)[1] for index in (0, 2, 4, 6))
    control = (10 - ((even + odd) % 10)) % 10
    return nif[8] in {str(control), _CIF_CONTROL[control]}


def _required(data: dict, keys: tuple[str, ...], labels: dict[str, str]) -> list[str]:
    return [f"{labels[key]} es obligatorio." for key in keys if not str(data.get(key) or "").strip()]


def validar_parte(parte: Parte, rol: str) -> list[str]:
    data = dict(parte.datos or {})
    errors = []
    if parte.tipo_persona not in {"fisica", "juridica"}:
        errors.append("Selecciona si actua como persona fisica o juridica.")
    if not parte.nombre.strip():
        errors.append("El nombre o razon social es obligatorio.")
    if not validar_nif(parte.nif):
        errors.append("El NIF, NIE o CIF no es valido.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", parte.email.strip()):
        errors.append("El correo electronico no es valido.")
    phone = re.sub(r"\D", "", parte.telefono)
    if not 9 <= len(phone) <= 15:
        errors.append("El telefono debe contener entre 9 y 15 digitos.")

    common_labels = {
        "direccion": "La direccion",
        "cp": "El codigo postal",
        "poblacion": "La poblacion",
        "provincia": "La provincia",
    }
    errors.extend(_required(data, tuple(common_labels), common_labels))
    if data.get("cp") and not re.fullmatch(r"\d{5}", str(data["cp"]).strip()):
        errors.append("El codigo postal debe tener 5 digitos.")

    if parte.tipo_persona == "juridica":
        errors.extend(
            _required(
                data,
                ("representante_nombre", "representante_nif"),
                {
                    "representante_nombre": "El nombre del representante",
                    "representante_nif": "El DNI o NIE del representante",
                },
            )
        )
        if data.get("representante_nif") and not validar_nif(str(data["representante_nif"])):
            errors.append("El DNI o NIE del representante no es valido.")

    if rol == "vendedor":
        labels = {
            "vehiculo_matricula": "La matricula",
            "vehiculo_bastidor": "El numero de bastidor",
            "vehiculo_marca": "La marca",
            "vehiculo_modelo": "El modelo y version",
            "primera_matriculacion": "La fecha de primera matriculacion",
            "kilometraje": "El kilometraje",
            "precio_venta": "El precio de venta",
            "fecha_operacion": "La fecha de entrega",
            "hora_entrega": "La hora de entrega",
            "forma_pago": "La forma de pago",
            "llaves_vehiculo": "El numero de llaves",
        }
        errors.extend(_required(data, tuple(labels), labels))
        matricula = re.sub(r"[^A-Z0-9]", "", str(data.get("vehiculo_matricula") or "").upper())
        if matricula and not re.fullmatch(r"[A-Z0-9]{5,10}", matricula):
            errors.append("La matricula no tiene un formato valido.")
        bastidor = str(data.get("vehiculo_bastidor") or "").upper()
        if bastidor and not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", bastidor):
            errors.append("El bastidor debe tener 17 caracteres y no puede contener I, O o Q.")
        for key, label, positive in (
            ("kilometraje", "El kilometraje", False),
            ("precio_venta", "El precio de venta", True),
            ("llaves_vehiculo", "El numero de llaves", True),
        ):
            try:
                value = float(str(data.get(key) or "").replace(",", "."))
                if value < 0 or (positive and value <= 0):
                    raise ValueError
            except ValueError:
                errors.append(f"{label} debe ser un numero valido.")
        for key, label in (
            ("primera_matriculacion", "La primera matriculacion"),
            ("fecha_operacion", "La fecha de entrega"),
        ):
            try:
                parsed = date.fromisoformat(str(data.get(key) or ""))
                if parsed > date.today():
                    errors.append(f"{label} no puede ser futura.")
            except ValueError:
                errors.append(f"{label} no contiene una fecha valida.")
    else:
        shipping_labels = {
            "direccion_envio": "La direccion de envio",
            "cp_envio": "El codigo postal de envio",
            "poblacion_envio": "La poblacion de envio",
            "provincia_envio": "La provincia de envio",
        }
        errors.extend(_required(data, tuple(shipping_labels), shipping_labels))
        if data.get("cp_envio") and not re.fullmatch(r"\d{5}", str(data["cp_envio"]).strip()):
            errors.append("El codigo postal de envio debe tener 5 digitos.")
    return errors
