from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT_DOCX = ROOT / "output" / "documentos" / "Manual_Mensajeria_Gestinem.docx"
LOGIN_CAPTURE = WORK / "01-acceso-clientes.png"
PHONE_CAPTURE = Path(
    r"C:\Users\GestinemFiscal\Gest2A3Eco\.codex-remote-attachments\019fe198-7886-76d2-9470-1048d1873012\91700766-a988-4721-8e23-532c3145a0ef\1-Photo-1.jpg"
)
LOGO = ROOT / "backend" / "dgt_api" / "web" / "static" / "gestinem-logo.png"
ICON = ROOT / "backend" / "dgt_api" / "web" / "static" / "gestinem-icon-512.png"
URL = "https://gest2a3eco-production.up.railway.app/mensajes"

NAVY = "00345D"
BLUE = "0759AF"
LIGHT = "EEF3F8"
PALE = "F5F8FB"
INK = "183247"
MUTED = "5D6B78"
GREEN = "18794E"
WHITE = "FFFFFF"


def rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color)


def font(size: int, bold: bool = False):
    candidates = [
        Path(r"C:\Windows\Fonts\seguisb.ttf") if bold else Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf") if bold else Path(r"C:\Windows\Fonts\arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def rounded(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def make_install_guide() -> Path:
    source = Image.open(PHONE_CAPTURE).convert("RGB")
    toolbar = source.crop((0, 0, source.width, 145))
    canvas = Image.new("RGB", (1200, 720), "white")
    draw = ImageDraw.Draw(canvas)
    toolbar.thumbnail((1080, 265), Image.Resampling.LANCZOS)
    canvas.paste(toolbar, ((1200 - toolbar.width) // 2, 45))

    draw.ellipse((1055, 56, 1125, 126), fill="#E74C3C")
    draw.text((1090, 91), "1", font=font(34, True), fill="white", anchor="mm")
    draw.line((1055, 125, 980, 175), fill="#E74C3C", width=7)

    rounded(draw, (80, 285, 1120, 620), 28, "#F4F7FA", outline="#D8E1E8", width=3)
    steps = [
        ("1", "Abra el enlace", "Escriba la dirección en Brave\no Chrome."),
        ("2", "Pulse el menú", "Está en la esquina superior\nderecha."),
        ("3", "Instalar aplicación", "Confirme la instalación y abra\nel icono de la G."),
    ]
    xs = [240, 600, 960]
    for (number, title, detail), x in zip(steps, xs):
        draw.ellipse((x - 32, 322, x + 32, 386), fill="#0759AF")
        draw.text((x, 354), number, font=font(30, True), fill="white", anchor="mm")
        draw.text((x, 425), title, font=font(29, True), fill="#00345D", anchor="mm")
        draw.multiline_text((x, 480), detail, font=font(22), fill="#34495E", anchor="ma", align="center", spacing=8)
    icon = Image.open(ICON).convert("RGB").resize((86, 86), Image.Resampling.LANCZOS)
    canvas.paste(icon, (917, 525))
    draw.text((600, 674), "Vista orientativa: el texto del menú puede variar ligeramente según el navegador.", font=font(18), fill="#667788", anchor="mm")
    path = WORK / "02-instalar-en-brave.png"
    canvas.save(path, optimize=True)
    return path


def make_chat_guide() -> Path:
    canvas = Image.new("RGB", (900, 1350), "#F4F7FA")
    draw = ImageDraw.Draw(canvas)
    rounded(draw, (55, 35, 845, 1315), 32, "white", outline="#D6E0E8", width=3)
    logo = Image.open(LOGO).convert("RGBA")
    logo.thumbnail((300, 110), Image.Resampling.LANCZOS)
    canvas.paste(logo, (90, 80), logo)
    rounded(draw, (570, 78, 790, 142), 16, "#E8F2FB")
    draw.text((680, 110), "Activar avisos", font=font(23, True), fill="#00345D", anchor="mm")
    draw.text((90, 205), "CONVERSACIONES", font=font(19, True), fill="#667788")

    channels = [("Laboral", False), ("Contable / Fiscal", True), ("Privado", False)]
    y = 242
    for label, active in channels:
        rounded(draw, (90, y, 810, y + 80), 18, "#0759AF" if active else "#EEF3F8")
        draw.text((125, y + 40), label, font=font(27, True), fill="white" if active else "#00345D", anchor="lm")
        y += 98

    draw.line((90, 548, 810, 548), fill="#DCE4EA", width=2)
    draw.text((90, 590), "Contable / Fiscal", font=font(31, True), fill="#00345D")
    rounded(draw, (90, 655, 650, 790), 20, "#EEF3F8")
    draw.text((120, 682), "Gestinem · hoy, 10:15", font=font(18, True), fill="#5D6B78")
    draw.multiline_text((120, 724), "Buenos días. Puede enviarnos aquí la\nfactura y quedará vinculada a su ficha.", font=font(23), fill="#183247", spacing=7)

    rounded(draw, (255, 820, 810, 970), 20, "#0759AF")
    draw.text((285, 850), "Empresa Ejemplo · hoy, 10:18", font=font(18, True), fill="white")
    draw.text((285, 893), "Adjunto la factura de julio.", font=font(23), fill="white")
    rounded(draw, (285, 925, 660, 958), 10, "#E7F2FB")
    draw.text((305, 942), "PDF  factura_julio.pdf", font=font(18, True), fill="#00345D", anchor="lm")

    rounded(draw, (90, 1030, 810, 1115), 16, "white", outline="#BFCBD5", width=2)
    draw.text((120, 1072), "Escribe un mensaje", font=font(22), fill="#7B8792", anchor="lm")
    rounded(draw, (90, 1140, 310, 1210), 15, "#EEF3F8")
    draw.text((200, 1175), "Adjuntar", font=font(23, True), fill="#00345D", anchor="mm")
    rounded(draw, (590, 1140, 810, 1210), 15, "#0759AF")
    draw.text((700, 1175), "Enviar", font=font(23, True), fill="white", anchor="mm")
    draw.text((450, 1270), "Vista orientativa de una conversación de cliente.", font=font(18), fill="#667788", anchor="mm")
    path = WORK / "03-canales-y-adjuntos.png"
    canvas.save(path, optimize=True)
    return path


def make_notification_guide() -> Path:
    source = Image.open(PHONE_CAPTURE).convert("RGB")
    header = source.crop((0, 110, 385, 235)).resize((770, 250), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1000, 430), "white")
    draw = ImageDraw.Draw(canvas)
    canvas.paste(header, (40, 45))
    draw.ellipse((735, 30, 805, 100), fill="#E74C3C")
    draw.text((770, 65), "1", font=font(32, True), fill="white", anchor="mm")
    draw.line((748, 100, 660, 156), fill="#E74C3C", width=7)
    rounded(draw, (70, 325, 930, 405), 18, "#EAF6EF", outline="#B9DFC8", width=2)
    draw.text((500, 365), "Pulse Activar avisos y después Permitir.", font=font(28, True), fill="#18794E", anchor="mm")
    path = WORK / "04-activar-avisos.png"
    canvas.save(path, optimize=True)
    return path


def set_cell_shading(paragraph, fill: str):
    p_pr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    p_pr.append(shd)


def set_repeat_font(run, name="Calibri", size=None, color=None, bold=None, italic=None):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    if size is not None:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = rgb(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_style(style, size, color, bold, before, after, line_spacing=1.0):
    style.font.name = "Calibri"
    style._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Calibri")
    style._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Calibri")
    style.font.size = Pt(size)
    style.font.color.rgb = rgb(color)
    style.font.bold = bold
    style.paragraph_format.space_before = Pt(before)
    style.paragraph_format.space_after = Pt(after)
    style.paragraph_format.line_spacing = line_spacing


def configure_numbering(doc: Document, *, bullet: bool = False) -> int:
    numbering = doc.part.numbering_part.element
    target = "bullet" if bullet else "decimal"
    abstract_id = None
    for abstract in numbering.findall(qn("w:abstractNum")):
        fmt = abstract.find("./w:lvl[@w:ilvl='0']/w:numFmt", {"w": qn("w:val").split("}")[0][1:]})
        if fmt is not None and fmt.get(qn("w:val")) == target:
            abstract_id = int(abstract.get(qn("w:abstractNumId")))
            break
    if abstract_id is None:
        raise RuntimeError(f"No existe una definición de lista {target} en la plantilla de Word")
    num_id = max([int(el.get(qn("w:numId"))) for el in numbering.findall(qn("w:num"))], default=0) + 1
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    ref = OxmlElement("w:abstractNumId")
    ref.set(qn("w:val"), str(abstract_id))
    num.append(ref)
    if not bullet:
        override = OxmlElement("w:lvlOverride")
        override.set(qn("w:ilvl"), "0")
        start_override = OxmlElement("w:startOverride")
        start_override.set(qn("w:val"), "1")
        override.append(start_override)
        num.append(override)
    numbering.append(num)
    return num_id


def add_numbered(doc: Document, text: str, num_id: int):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.375)
    p.paragraph_format.first_line_indent = Inches(-0.188)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.25
    p_pr = p._p.get_or_add_pPr()
    num_pr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    num = OxmlElement("w:numId")
    num.set(qn("w:val"), str(num_id))
    num_pr.extend([ilvl, num])
    p_pr.append(num_pr)
    set_repeat_font(p.add_run(text), size=11, color=INK)
    return p


def add_hyperlink(paragraph, text: str, url: str):
    rel_id = paragraph.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rel_id)
    run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), BLUE)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    r_pr.extend([color, underline])
    text_el = OxmlElement("w:t")
    text_el.text = text
    run.extend([r_pr, text_el])
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_callout(doc: Document, title: str, body: str, fill=LIGHT, accent=NAVY):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.18)
    p.paragraph_format.right_indent = Inches(0.18)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(10)
    p.paragraph_format.line_spacing = 1.15
    set_cell_shading(p, fill)
    set_repeat_font(p.add_run(title + "\n"), size=11, color=accent, bold=True)
    set_repeat_font(p.add_run(body), size=10.5, color=INK)
    return p


def add_figure(doc: Document, path: Path, width: float, caption: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(3)
    picture = p.add_run().add_picture(str(path), width=Inches(width))
    picture._inline.docPr.set("descr", caption)
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_before = Pt(0)
    cap.paragraph_format.space_after = Pt(8)
    set_repeat_font(cap.add_run(caption), size=8.5, color=MUTED, italic=True)


def add_page_field(paragraph):
    run = paragraph.add_run()
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    run._r.extend([fld_char1, instr, fld_char2])
    set_repeat_font(run, size=8.5, color=MUTED)


def new_page(doc: Document, title: str, subtitle: str | None = None):
    doc.add_page_break()
    p = doc.add_paragraph(style="Heading 1")
    p.paragraph_format.keep_with_next = True
    p.add_run(title)
    if subtitle:
        sub = doc.add_paragraph()
        sub.paragraph_format.space_after = Pt(12)
        set_repeat_font(sub.add_run(subtitle), size=11, color=MUTED)


def build_document():
    install_guide = make_install_guide()
    chat_guide = make_chat_guide()
    notification_guide = make_notification_guide()
    login = Image.open(LOGIN_CAPTURE).convert("RGB").crop((0, 0, 412, 570))
    login_path = WORK / "01-acceso-clientes-recortada.png"
    login.save(login_path, optimize=True)

    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    styles = doc.styles
    set_style(styles["Normal"], 11, INK, False, 0, 6, 1.25)
    set_style(styles["Heading 1"], 16, NAVY, True, 18, 10, 1.0)
    set_style(styles["Heading 2"], 13, BLUE, True, 14, 7, 1.0)
    set_style(styles["Heading 3"], 12, NAVY, True, 10, 5, 1.0)

    # Override editorial: se omite el encabezado corrido para que las capturas
    # dispongan de más aire y el PDF sea idéntico en páginas pares e impares.
    doc.settings.odd_and_even_pages_header_footer = True
    for footer_part in (section.footer, section.even_page_footer):
        footer = footer_part.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_repeat_font(footer.add_run("Gestinem · Comunicación segura · "), size=8.5, color=MUTED)
        add_page_field(footer)

    # Portada editorial con identidad corporativa.
    p_logo = doc.add_paragraph()
    p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_logo.paragraph_format.space_before = Pt(55)
    p_logo.paragraph_format.space_after = Pt(36)
    cover_logo = p_logo.add_run().add_picture(str(LOGO), width=Inches(3.25))
    cover_logo._inline.docPr.set("descr", "Logotipo corporativo de Gestinem")
    kicker = doc.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kicker.paragraph_format.space_after = Pt(12)
    set_repeat_font(kicker.add_run("NUEVO CANAL DE COMUNICACIÓN"), size=10, color=BLUE, bold=True)
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(10)
    set_repeat_font(title.add_run("Mensajería Gestinem"), size=29, color=NAVY, bold=True)
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(30)
    set_repeat_font(subtitle.add_run("Guía rápida para clientes"), size=15, color=MUTED)
    icon_p = doc.add_paragraph()
    icon_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    icon_p.paragraph_format.space_after = Pt(24)
    cover_icon = icon_p.add_run().add_picture(str(ICON), width=Inches(1.25))
    cover_icon._inline.docPr.set("descr", "Icono corporativo de Gestinem con la letra G")
    add_callout(
        doc,
        "Una comunicación más ordenada y segura",
        "Queremos sustituir progresivamente las conversaciones de WhatsApp por la Mensajería Gestinem. Así, sus consultas y documentos llegarán al equipo adecuado y quedarán vinculados a su relación con el despacho.",
        fill=LIGHT,
        accent=NAVY,
    )
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_repeat_font(p.add_run("Acceso desde móvil, tableta u ordenador · No necesita instalar Gest2A3Eco"), size=9.5, color=MUTED, italic=True)

    new_page(doc, "1. ¿Por qué cambiamos WhatsApp?")
    doc.add_paragraph(
        "La Mensajería Gestinem reúne en un único lugar las conversaciones del cliente con el despacho. El cambio evita depender de teléfonos personales y permite que cada consulta sea atendida por las personas responsables."
    )
    for heading, text in [
        ("Laboral", "Consultas y documentación de nóminas, contratos, altas, bajas y Seguridad Social."),
        ("Contable / Fiscal", "Facturas, impuestos, contabilidad y documentación económica."),
        ("Privado", "Conversación directa y reservada con la dirección del despacho."),
    ]:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(7)
        set_repeat_font(p.add_run(heading + ". "), size=11, color=NAVY, bold=True)
        set_repeat_font(p.add_run(text), size=11, color=INK)
    add_callout(
        doc,
        "Importante",
        "Use el canal correspondiente para que su mensaje llegue desde el primer momento al equipo que debe gestionarlo. Los documentos enviados quedan disponibles para su incorporación al expediente o a la gestión documental.",
        fill="FFF7E8",
        accent="7A5A00",
    )
    h = doc.add_paragraph(style="Heading 2")
    h.add_run("Qué necesita")
    num_id = configure_numbering(doc)
    add_numbered(doc, "Una invitación enviada por Gestinem a su correo electrónico.", num_id)
    add_numbered(doc, "Un navegador actualizado: Brave, Chrome, Edge o Safari.", num_id)
    add_numbered(doc, "Una contraseña personal de al menos 10 caracteres.", num_id)

    new_page(doc, "2. Primer acceso", "Active su cuenta desde la invitación y entre con su correo habitual.")
    num_id = configure_numbering(doc)
    add_numbered(doc, "Abra el correo de invitación de Gestinem y pulse el enlace de activación.", num_id)
    add_numbered(doc, "Cree una contraseña de al menos 10 caracteres y guárdela de forma segura.", num_id)
    add_numbered(doc, "Entre con su email y contraseña desde la dirección que aparece debajo.", num_id)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    add_hyperlink(p, "Abrir Mensajería Gestinem", URL)
    url_text = doc.add_paragraph()
    url_text.alignment = WD_ALIGN_PARAGRAPH.CENTER
    url_text.paragraph_format.space_after = Pt(8)
    set_repeat_font(url_text.add_run(URL), size=8.5, color=MUTED)
    add_figure(doc, login_path, 3.05, "Pantalla real de acceso al Área de clientes.")
    add_callout(
        doc,
        "¿Ha olvidado la contraseña?",
        "Pulse ¿Has olvidado tu contraseña? en la pantalla de acceso. Recibirá un enlace seguro para crear una nueva.",
        fill=PALE,
        accent=BLUE,
    )

    new_page(doc, "3. Instalar la aplicación", "La instalación crea un icono de la G y abre la mensajería como una aplicación independiente.")
    h = doc.add_paragraph(style="Heading 2")
    h.add_run("Android: Brave o Chrome")
    num_id = configure_numbering(doc)
    add_numbered(doc, "Abra directamente la dirección de Mensajería Gestinem en Brave o Chrome.", num_id)
    add_numbered(doc, "Pulse el menú de tres puntos (⋮) y elija Instalar aplicación.", num_id)
    add_numbered(doc, "Confirme y abra el nuevo icono de la G desde la pantalla de inicio.", num_id)
    add_figure(doc, install_guide, 6.25, "Instalación en Android con Brave. Los nombres del menú pueden variar ligeramente.")
    h = doc.add_paragraph(style="Heading 2")
    h.add_run("iPhone o iPad")
    doc.add_paragraph("Abra el enlace en Safari, pulse Compartir y seleccione Añadir a pantalla de inicio.")
    h = doc.add_paragraph(style="Heading 2")
    h.add_run("Ordenador")
    doc.add_paragraph("En Edge o Chrome, abra el enlace y pulse el icono Instalar situado en la barra de direcciones o en el menú del navegador.")
    add_callout(doc, "Si solo aparece «Añadir a pantalla de inicio»", "Recargue la página, espere unos segundos y compruebe que la ha abierto directamente en Brave o Chrome, no dentro del navegador interno de otra aplicación.", fill="FFF7E8", accent="7A5A00")

    new_page(doc, "4. Enviar mensajes y documentos")
    doc.add_paragraph("Seleccione Laboral, Contable / Fiscal o Privado antes de escribir. La conversación muestra quién ha respondido desde Gestinem y conserva el historial del canal.")
    add_figure(doc, chat_guide, 3.45, "Vista orientativa de los canales, mensajes y adjuntos.")
    h = doc.add_paragraph(style="Heading 2")
    h.add_run("Adjuntar un documento")
    num_id = configure_numbering(doc)
    add_numbered(doc, "Entre en el canal relacionado con el documento.", num_id)
    add_numbered(doc, "Pulse Adjuntar y seleccione uno o varios archivos.", num_id)
    add_numbered(doc, "Compruebe el nombre del archivo y pulse Enviar una sola vez.", num_id)
    add_callout(doc, "Formatos habituales", "Puede enviar PDF, imágenes, documentos de Word, hojas de cálculo, XML, CSV y ZIP. Use nombres claros, por ejemplo: Factura_Luz_Julio_2026.pdf.", fill=LIGHT, accent=NAVY)

    new_page(doc, "5. Activar avisos", "Reciba una notificación aunque la mensajería no esté abierta.")
    add_figure(doc, notification_guide, 6.1, "Botón para activar las notificaciones en el dispositivo.")
    num_id = configure_numbering(doc)
    add_numbered(doc, "Entre en Mensajería Gestinem y pulse Activar avisos.", num_id)
    add_numbered(doc, "Cuando el navegador lo solicite, pulse Permitir.", num_id)
    add_numbered(doc, "Si aparece Avisos activos, la configuración ha terminado.", num_id)
    add_callout(doc, "Si los avisos están bloqueados", "Abra Ajustes del teléfono > Aplicaciones > Brave, Chrome o Gestinem > Notificaciones y permita los avisos. Después vuelva a abrir la aplicación.", fill="FFF7E8", accent="7A5A00")
    h = doc.add_paragraph(style="Heading 2")
    h.add_run("Buenas prácticas")
    bullet_num_id = configure_numbering(doc, bullet=True)
    for text in [
        "No comparta su contraseña con nadie, incluido el personal de Gestinem.",
        "Evite enviar el mismo documento varias veces si tarda unos segundos en aparecer.",
        "Para consultas urgentes o problemas de acceso, contacte con Gestinem por los medios habituales.",
    ]:
        add_numbered(doc, text, bullet_num_id)
    closing = doc.add_paragraph()
    closing.alignment = WD_ALIGN_PARAGRAPH.CENTER
    closing.paragraph_format.space_before = Pt(22)
    set_repeat_font(closing.add_run("Gracias por ayudarnos a ofrecerle una atención más rápida, segura y organizada."), size=12, color=NAVY, bold=True)

    doc.core_properties.title = "Mensajería Gestinem - Guía rápida para clientes"
    doc.core_properties.subject = "Acceso, instalación, canales, adjuntos y notificaciones"
    doc.core_properties.author = "Gestinem"
    doc.core_properties.keywords = "Gestinem, mensajería, clientes, PWA, comunicaciones"
    OUT_DOCX.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT_DOCX)
    print(OUT_DOCX)


if __name__ == "__main__":
    build_document()
