import pandas as pd


def col_letter_to_index(letter: str) -> int:
    letter = "" if letter is None else str(letter)
    letter = letter.strip().upper()
    if not letter:
        return -1
    idx = 0
    for ch in letter:
        if not ("A" <= ch <= "Z"):
            return -1
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def extract_rows_by_mapping(xlsx_path: str, sheet: str, mapping: dict):
    raw = pd.read_excel(xlsx_path, sheet_name=sheet, header=None, dtype=object)
    first = int((mapping or {}).get("primera_fila_procesar", 2))
    start_idx = max(0, first - 1)
    cols_map = (mapping or {}).get("columnas", {}) or {}
    ign = str((mapping or {}).get("ignorar_filas", "") or "").strip()
    gen = str((mapping or {}).get("condicion_cuenta_generica", "") or "").strip()

    def pick(row, letter):
        ci = col_letter_to_index(letter)
        if ci < 0 or ci >= len(row):
            return None
        return row.iloc[ci]

    def parse_cond(cond):
        if "=" not in cond:
            return None, None
        a, b = cond.split("=", 1)
        return a.strip().upper(), b

    ign_col, ign_val = parse_cond(ign)
    gen_col, gen_val = parse_cond(gen)

    rows = []
    for r in range(start_idx, len(raw)):
        row = raw.iloc[r]
        if ign_col:
            cidx = col_letter_to_index(ign_col)
            if 0 <= cidx < len(row) and str(row.iloc[cidx]).strip() == str(ign_val):
                continue
        rec = {}
        for k, letter in cols_map.items():
            rec[k] = pick(row, letter) if letter else None
        rec["_usar_cuenta_generica"] = False
        if gen_col:
            cidx = col_letter_to_index(gen_col)
            if 0 <= cidx < len(row) and str(row.iloc[cidx]).strip() == str(gen_val):
                rec["_usar_cuenta_generica"] = True
        rows.append(rec)
    return rows
