import re


_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_CIF_CONTROL = "JABCDEFGHI"
_CIF_LETTER_TYPES = set("KPQS")
_CIF_DIGIT_TYPES = set("ABEH")


def _norm_nif(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()


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
