import os
import struct


def _to_float(x) -> float:
    try:
        if x is None or x == "":
            return 0.0
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return float(x)
        s = str(x).strip().replace("\xa0", " ")
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return 0.0


def _round2(x) -> float:
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0


def _pdf_escape(text: str) -> str:
    return str(text or "").replace("\\", "\\\\").replace("(", "[").replace(")", "]")


def _logo_jpeg(path: str):
    if not path or not os.path.exists(path):
        return None
    if not path.lower().endswith((".jpg", ".jpeg")):
        return None
    try:
        with open(path, "rb") as f:
            data = f.read()
        i = 0
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if i + 9 >= len(data):
                    break
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                comp = data[i + 9] if i + 9 < len(data) else 3
                return {"data": data, "w": w, "h": h, "components": comp}
            if i + 4 >= len(data):
                break
            seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
            i += seg_len + 2
    except Exception:
        return None
    return None


def generar_pdf_basico(empresa_conf: dict, fac: dict, cliente: dict, totales: dict, out_pdf_path: str) -> None:
    def t(x, y, txt, size=11, bold=False):
        font = "F2" if bold else "F1"
        return f"BT /{font} {size} Tf 1 0 0 1 {x} {y} Tm ({_pdf_escape(txt)}) Tj ET\n"

    y = 800
    body = []
    logo = _logo_jpeg(str(empresa_conf.get("logo_path") or "").strip())
    logo_cmd = ""
    if logo:
        disp_w = 120
        disp_h = max(40, int(logo["h"] * disp_w / max(logo["w"], 1)))
        logo_cmd = f"q {disp_w} 0 0 {disp_h} 50 {y - disp_h + 10} cm /Im1 Do Q\n"
        y -= disp_h + 10

    body.append(t(50, y, "Factura emitida", 16, True))
    y -= 24

    emitter = empresa_conf or {}
    body.append(t(50, y, emitter.get("nombre") or "", 12, True))
    y -= 14
    body.append(t(50, y, f"CIF: {emitter.get('cif','')}", 10))
    y -= 12
    dir_line = ", ".join(filter(None, [emitter.get("direccion"), emitter.get("cp"), emitter.get("poblacion")]))
    if dir_line:
        body.append(t(50, y, dir_line, 10))
        y -= 12
    prov_line = ", ".join(filter(None, [emitter.get("provincia"), emitter.get("telefono"), emitter.get("email")]))
    if prov_line:
        body.append(t(50, y, prov_line, 10))
        y -= 12
    info_eje = emitter.get("ejercicio", "")
    body.append(t(50, y, f"Ejercicio: {info_eje}  Serie: {fac.get('serie','') or '-'}", 10))
    y -= 18

    box_w, box_h = 260, 70
    box_x, box_y = 320, y
    body.append(f"q 1 w {box_x} {box_y - box_h} {box_w} {box_h} re S Q\n")
    body.append(t(box_x + 8, box_y - 14, "Cliente", 12, True))
    body.append(t(box_x + 8, box_y - 28, f"{cliente.get('nombre','')}", 10))
    body.append(t(box_x + 8, box_y - 42, f"NIF: {cliente.get('nif','')}", 10))
    addr = ", ".join(filter(None, [cliente.get("direccion"), cliente.get("cp"), cliente.get("poblacion")]))
    if addr:
        body.append(t(box_x + 8, box_y - 56, addr, 10))
    contacto = ", ".join(filter(None, [cliente.get("provincia"), cliente.get("telefono"), cliente.get("email")]))
    if contacto:
        body.append(t(box_x + 8, box_y - 70, contacto, 10))
    y = min(y, box_y - box_h - 12)

    y -= 4
    body.append(t(50, y, f"Factura: {fac.get('serie','')}-{fac.get('numero','')}", 11, True))
    body.append(t(260, y, f"Fecha: {fac.get('fecha_expedicion') or fac.get('fecha_asiento','')}", 11))
    obs = fac.get("descripcion") or ""
    if obs:
        y -= 12
        body.append(t(50, y, f"Observaciones: {obs}", 10))
    y -= 16

    headers = [
        ("Concepto", 50),
        ("Unid", 270),
        ("P. unit", 320),
        ("Base", 380),
        ("% IVA", 440),
        ("Cuota IVA", 490),
        ("% IRPF", 545),
    ]
    for txt, x in headers:
        body.append(t(x, y, txt, 11, True))
    y -= 12

    for ln in fac.get("lineas", []):
        body.append(t(50, y, str(ln.get("concepto", ""))[:42], 10))
        body.append(t(270, y, f"{_to_float(ln.get('unidades')):.2f}", 10))
        body.append(t(320, y, f"{_to_float(ln.get('precio')):.2f}", 10))
        body.append(t(380, y, f"{_to_float(ln.get('base')):.2f}", 10))
        body.append(t(440, y, f"{_to_float(ln.get('pct_iva')):.2f}%", 10))
        body.append(t(490, y, f"{_to_float(ln.get('cuota_iva')):.2f}", 10))
        body.append(t(545, y, f"{_to_float(ln.get('pct_irpf')):.2f}%", 10))
        y -= 12

    resumen = {}
    for ln in fac.get("lineas", []):
        pct = _round2(_to_float(ln.get("pct_iva")))
        item = resumen.setdefault(pct, {"base": 0.0, "cuota": 0.0})
        item["base"] += _to_float(ln.get("base"))
        item["cuota"] += _to_float(ln.get("cuota_iva"))

    y -= 16
    if resumen:
        body.append(t(360, y, "Detalle IVA:", 11, True))
        y -= 12
        body.append(t(360, y, "Tipo", 10, True))
        body.append(t(430, y, "Base", 10, True))
        body.append(t(500, y, "Cuota", 10, True))
        y -= 12
        for pct in sorted(resumen.keys(), reverse=True):
            item = resumen[pct]
            body.append(t(360, y, f"{pct:.2f}%", 10))
            body.append(t(430, y, f"{_round2(item['base']):.2f}", 10))
            body.append(t(500, y, f"{_round2(item['cuota']):.2f}", 10))
            y -= 12
        y -= 4

    body.append(t(360, y, "Base imponible:", 11, True))
    body.append(t(500, y, f"{_round2(totales.get('base')):.2f}", 11))
    y -= 14
    body.append(t(360, y, "IVA:", 11, True))
    body.append(t(500, y, f"{_round2(totales.get('iva')):.2f}", 11))
    y -= 14
    if abs(_to_float(totales.get("re"))) > 0.001:
        body.append(t(360, y, "Recargo Eq.:", 11, True))
        body.append(t(500, y, f"{_round2(totales.get('re')):.2f}", 11))
        y -= 14
    if abs(_to_float(totales.get("ret"))) > 0.001:
        body.append(t(360, y, "IRPF:", 11, True))
        body.append(t(500, y, f"{_round2(totales.get('ret')):.2f}", 11))
        y -= 16
    body.append(t(360, y, "Total factura:", 12, True))
    body.append(t(500, y, f"{_round2(totales.get('total')):.2f}", 12, True))

    content_parts = []
    if logo_cmd:
        content_parts.append(logo_cmd)
    content_parts.extend(body)
    stream = "".join(content_parts).encode("latin-1", "ignore")
    objs = []
    objs.append("1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objs.append("2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objs.append(None)
    objs.append(f"4 0 obj << /Length {len(stream)} >> stream\n".encode() + stream + b"endstream\nendobj\n")
    objs.append("5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objs.append("6 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> endobj\n")

    xobject_ref = ""
    if logo:
        color_space = "/DeviceGray" if logo["components"] == 1 else "/DeviceRGB"
        objs.append(
            f"7 0 obj << /Type /XObject /Subtype /Image /Width {logo['w']} /Height {logo['h']} "
            f"/ColorSpace {color_space} /BitsPerComponent 8 /Filter /DCTDecode /Length {len(logo['data'])} >> stream\n".encode()
            + logo["data"]
            + b"endstream\nendobj\n"
        )
        xobject_ref = "/XObject << /Im1 7 0 R >>"

    res_parts = ["/Font << /F1 5 0 R /F2 6 0 R >>"]
    if xobject_ref:
        res_parts.append(xobject_ref)
    page_res = "/Resources << " + " ".join(res_parts) + " >>"
    objs[2] = (
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        f"/Contents 4 0 R {page_res} >> endobj\n"
    )
    with open(out_pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\n")
        offsets = []
        for ob in objs:
            ob_bytes = ob if isinstance(ob, bytes) else ob.encode("latin-1")
            offsets.append(f.tell())
            f.write(ob_bytes)
        xref_pos = f.tell()
        f.write(f"xref\n0 {len(objs)+1}\n".encode())
        f.write(b"0000000000 65535 f \n")
        for off in offsets:
            f.write(f"{off:010d} 00000 n \n".encode())
        f.write(f"trailer << /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode())
