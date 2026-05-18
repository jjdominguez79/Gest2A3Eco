import re


_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_CIF_CONTROL = "JABCDEFGHI"
_CIF_LETTER_TYPES = set("KPQS")
_CIF_DIGIT_TYPES = set("ABEH")
_VAT_SIMPLE_PATTERNS = {
    "AT": r"U\d{8}",
    "BE": r"\d{10}",
    "BG": r"\d{9,10}",
    "CY": r"\d{8}[A-Z]",
    "CZ": r"\d{8,10}",
    "DE": r"\d{9}",
    "DK": r"\d{8}",
    "EE": r"\d{9}",
    "EL": r"\d{9}",
    "ES": r"[A-Z0-9]\d{7}[A-Z0-9]|\d{8}[A-Z]|[XYZ]\d{7}[A-Z]",
    "FI": r"\d{8}",
    "FR": r"[A-HJ-NP-Z0-9]{2}\d{9}",
    "HR": r"\d{11}",
    "HU": r"\d{8}",
    "IE": r"\d[A-Z0-9+\*]\d{5}[A-Z]{1,2}",
    "IT": r"\d{11}",
    "LT": r"(\d{9}|\d{12})",
    "LU": r"\d{8}",
    "LV": r"\d{11}",
    "MT": r"\d{8}",
    "NL": r"\d{9}B\d{2}",
    "PL": r"\d{10}",
    "PT": r"\d{9}",
    "RO": r"\d{2,10}",
    "SE": r"\d{12}",
    "SI": r"\d{8}",
    "SK": r"\d{10}",
}


def normalizar_nif_cif(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()


def _norm_nif(value: str | None) -> str:
    return normalizar_nif_cif(value)


def _validar_dni(nif: str) -> bool:
    num = int(nif[:8])
    letra = nif[8]
    return _DNI_LETTERS[num % 23] == letra


def _validar_nie(nie: str) -> bool:
    mapa = {"X": "0", "Y": "1", "Z": "2"}
    num = mapa.get(nie[0])
    if num is None:
        return False
    return _validar_dni(num + nie[1:])


def _validar_cif(cif: str) -> bool:
    letra = cif[0]
    digits = cif[1:8]
    control = cif[8]

    sum_even = sum(int(digits[i]) for i in (1, 3, 5))
    sum_odd = 0
    for i in (0, 2, 4, 6):
        d = int(digits[i]) * 2
        sum_odd += (d // 10) + (d % 10)

    total = sum_even + sum_odd
    control_digit = (10 - (total % 10)) % 10
    control_letter = _CIF_CONTROL[control_digit]

    if letra in _CIF_DIGIT_TYPES:
        return control.isdigit() and int(control) == control_digit
    if letra in _CIF_LETTER_TYPES:
        return control.isalpha() and control == control_letter
    return (control.isdigit() and int(control) == control_digit) or (control.isalpha() and control == control_letter)


def validar_nif_cif_nie(value: str | None) -> bool:
    nif = _norm_nif(value)
    if not nif:
        return False
    if re.fullmatch(r"\d{8}[A-Z]", nif):
        return _validar_dni(nif)
    if re.fullmatch(r"[XYZ]\d{7}[A-Z]", nif):
        return _validar_nie(nif)
    if re.fullmatch(r"[A-Z]\d{7}[0-9A-J]", nif):
        return _validar_cif(nif)
    return False


def es_nif_iva_intracomunitario(value: str | None) -> bool:
    nif = _norm_nif(value)
    if len(nif) < 4:
        return False
    country = nif[:2]
    if country not in _VAT_SIMPLE_PATTERNS:
        return False
    body = nif[2:]
    pattern = _VAT_SIMPLE_PATTERNS[country]
    if not re.fullmatch(pattern, body):
        return False
    if country == "ES":
        return validar_nif_cif_nie(body)
    if country == "EL":
        return _validar_vat_gr(body)
    return True


def validar_nif_o_nif_iva_intracomunitario(value: str | None) -> bool:
    return validar_nif_cif_nie(value) or es_nif_iva_intracomunitario(value)


def _validar_vat_gr(body: str) -> bool:
    if not re.fullmatch(r"\d{9}", body):
        return False
    total = 0
    for idx, digit in enumerate(body[:8]):
        total += int(digit) * (2 ** (8 - idx))
    control = (total % 11) % 10
    return control == int(body[8])


def inferir_pais_desde_identificacion(value: str | None) -> str:
    nif = _norm_nif(value)
    if not nif:
        return ""
    if validar_nif_cif_nie(nif):
        return "ES"
    if es_nif_iva_intracomunitario(nif):
        return nif[:2]
    return ""


def normalizar_codigo_pais(value: str | None) -> str:
    if value is None:
        return ""
    raw = re.sub(r"[^A-Za-z]", "", str(value)).upper()
    return raw[:2]
