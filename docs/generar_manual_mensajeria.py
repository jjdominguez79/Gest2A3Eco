from __future__ import annotations

import html
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "Manual_Mensajeria_Gestinem.pdf"
ASSETS = ROOT / "gestinem_app" / "test" / "goldens" / "manual"
LOGO = ROOT / "gestinem_app" / "assets" / "images" / "logo.png"

WEB_URL = "https://app.gestinem.es"
ANDROID_URL = (
    "https://play.google.com/store/apps/details?id=es.gestinem.app"
)

PAGE_W, PAGE_H = A4
NAVY = colors.HexColor("#004B76")
BLUE = colors.HexColor("#1B91CF")
PALE_BLUE = colors.HexColor("#E6F2FA")
LIGHT = colors.HexColor("#F2F6F8")
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#52616B")
LINE = colors.HexColor("#D7E1E7")
AMBER = colors.HexColor("#FFF4D6")


BODY = ParagraphStyle(
    "Body",
    fontName="Helvetica",
    fontSize=10.2,
    leading=14.5,
    textColor=INK,
    alignment=TA_LEFT,
    spaceAfter=6,
)
SMALL = ParagraphStyle(
    "Small",
    parent=BODY,
    fontSize=8.6,
    leading=12,
    textColor=MUTED,
)
HEADING = ParagraphStyle(
    "Heading",
    fontName="Helvetica-Bold",
    fontSize=13,
    leading=16,
    textColor=NAVY,
    spaceAfter=5,
)
COVER_TITLE = ParagraphStyle(
    "CoverTitle",
    fontName="Helvetica-Bold",
    fontSize=24,
    leading=29,
    textColor=NAVY,
    alignment=TA_CENTER,
)
COVER_SUBTITLE = ParagraphStyle(
    "CoverSubtitle",
    fontName="Helvetica",
    fontSize=12,
    leading=17,
    textColor=INK,
    alignment=TA_CENTER,
)


def p(
    c: canvas.Canvas,
    text: str,
    x: float,
    top: float,
    width: float,
    style: ParagraphStyle = BODY,
) -> float:
    paragraph = Paragraph(text, style)
    _, height = paragraph.wrap(width, PAGE_H)
    paragraph.drawOn(c, x, top - height)
    return top - height


def box(
    c: canvas.Canvas,
    x: float,
    top: float,
    width: float,
    text: str,
    fill: colors.Color = PALE_BLUE,
) -> float:
    paragraph = Paragraph(text, BODY)
    _, height = paragraph.wrap(width - 24, PAGE_H)
    total = height + 20
    c.setFillColor(fill)
    c.roundRect(x, top - total, width, total, 6, fill=1, stroke=0)
    paragraph.drawOn(c, x + 12, top - 10 - height)
    return top - total


def footer(c: canvas.Canvas, page: int) -> None:
    c.setStrokeColor(LINE)
    c.line(42, 38, PAGE_W - 42, 38)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.4)
    c.drawString(42, 24, "Gestinem - Manual para clientes - Octubre de 2026")
    c.drawRightString(PAGE_W - 42, 24, str(page))


def page_title(c: canvas.Canvas, number: str, title: str, page: int) -> None:
    c.setFillColor(BLUE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(42, PAGE_H - 52, number)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(42, PAGE_H - 78, html.unescape(title))
    footer(c, page)


def phone_image(
    c: canvas.Canvas,
    filename: str,
    x: float = 46,
    top: float = PAGE_H - 110,
    height: float = 500,
) -> None:
    path = ASSETS / filename
    image = ImageReader(str(path))
    iw, ih = image.getSize()
    width = height * iw / ih
    c.setFillColor(colors.white)
    c.setStrokeColor(LINE)
    c.roundRect(x - 5, top - height - 5, width + 10, height + 10, 8, fill=1, stroke=1)
    c.drawImage(image, x, top - height, width=width, height=height, mask="auto")


def bullet(c: canvas.Canvas, text: str, x: float, top: float, width: float) -> float:
    return p(c, f"<bullet>&bull;</bullet>{text}", x, top, width, BODY) - 5


def screenshot_page(
    c: canvas.Canvas,
    *,
    page: int,
    number: str,
    title: str,
    image: str,
    intro: str,
    sections: list[tuple[str, list[str]]],
) -> None:
    page_title(c, number, title, page)
    phone_image(c, image)
    x = 292
    width = PAGE_W - x - 42
    c.setFillColor(colors.white)
    c.rect(x - 8, 46, PAGE_W - (x - 8), PAGE_H - 142, fill=1, stroke=0)
    top = PAGE_H - 112
    top = p(c, intro, x, top, width, BODY) - 12
    for heading, items in sections:
        top = p(c, heading, x, top, width, HEADING) - 3
        for item in items:
            top = bullet(c, item, x + 2, top, width - 2)
        top -= 4
    c.showPage()


def cover(c: canvas.Canvas) -> None:
    image = ImageReader(str(LOGO))
    iw, ih = image.getSize()
    logo_h = 130
    logo_w = logo_h * iw / ih
    c.drawImage(
        image,
        (PAGE_W - logo_w) / 2,
        PAGE_H - 235,
        width=logo_w,
        height=logo_h,
        mask="auto",
    )
    p(c, "Gestinem", 70, PAGE_H - 270, PAGE_W - 140, COVER_TITLE)
    p(
        c,
        "Manual de uso para clientes",
        70,
        PAGE_H - 310,
        PAGE_W - 140,
        COVER_SUBTITLE,
    )
    y = box(
        c,
        58,
        PAGE_H - 365,
        PAGE_W - 116,
        "<b>Versi&oacute;n actual.</b> Este manual reproduce la interfaz real de Gestinem en m&oacute;vil. "
        "La aplicaci&oacute;n est&aacute; publicada en Android y la versi&oacute;n para iPhone y iPad contin&uacute;a en revisi&oacute;n por Apple.",
    )
    y -= 30
    p(
        c,
        f'<link href="{WEB_URL}" color="#004B76"><u>Abrir Gestinem en el navegador</u></link>',
        90,
        y,
        PAGE_W - 180,
        ParagraphStyle("CoverLink", parent=BODY, alignment=TA_CENTER, fontName="Helvetica-Bold"),
    )
    p(
        c,
        f'<link href="{ANDROID_URL}" color="#004B76"><u>Descargar Gestinem Chat en Google Play</u></link>',
        90,
        y - 30,
        PAGE_W - 180,
        ParagraphStyle("CoverLink2", parent=BODY, alignment=TA_CENTER, fontName="Helvetica-Bold"),
    )
    p(
        c,
        "Mensajes, documentos, certificados y servicios de su empresa en un &uacute;nico espacio seguro.",
        85,
        190,
        PAGE_W - 170,
        ParagraphStyle(
            "CoverClaim",
            parent=COVER_SUBTITLE,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
        ),
    )
    footer(c, 1)
    c.showPage()


def activation(c: canvas.Canvas) -> None:
    page_title(c, "1", "Active su cuenta y entre en Gestinem", 2)
    y = PAGE_H - 112
    y = p(
        c,
        "La primera vez recibir&aacute; un correo de invitaci&oacute;n de Gestinem. El enlace es personal y caduca a las 72 horas.",
        58,
        y,
        PAGE_W - 116,
    )
    y -= 22
    for number, text in [
        ("1", "Abra el correo y pulse <b>Activar mi cuenta</b>."),
        ("2", "Cree una contrase&ntilde;a de al menos 10 caracteres y rep&iacute;tala para confirmarla."),
        ("3", "Pulse <b>Activar y entrar</b>. La cuenta queda activada y acceder&aacute; directamente."),
    ]:
        c.setFillColor(NAVY)
        c.roundRect(58, y - 23, 23, 23, 3, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(69.5, y - 16, number)
        y = p(c, text, 94, y - 2, PAGE_W - 152, BODY) - 16
    y -= 3
    y = box(
        c,
        58,
        y,
        PAGE_W - 116,
        f"<b>C&oacute;mo volver a entrar.</b> En Android abra Gestinem Chat. En un ordenador, m&oacute;vil o tableta tambi&eacute;n puede abrir "
        f'<link href="{WEB_URL}" color="#004B76"><u>{WEB_URL}</u></link>. El navegador y la aplicaci&oacute;n mantienen la contrase&ntilde;a durante la activaci&oacute;n.',
    )
    y -= 18
    y = box(
        c,
        58,
        y,
        PAGE_W - 116,
        "<b>Si olvid&oacute; la contrase&ntilde;a.</b> En la pantalla de acceso pulse <b>&iquest;Olvidaste tu contrase&ntilde;a?</b>. Recibir&aacute; un enlace seguro para crear una nueva contrase&ntilde;a.",
        AMBER,
    )
    y -= 26
    y = p(c, "Antes de continuar", 58, y, PAGE_W - 116, HEADING) - 4
    for item in [
        f'Compruebe que el navegador muestra <link href="{WEB_URL}" color="#004B76"><u>{WEB_URL}</u></link>.',
        "No reenv&iacute;e el correo de invitaci&oacute;n ni comparta su contrase&ntilde;a.",
        "En Android, permita las notificaciones cuando la aplicaci&oacute;n se lo solicite.",
        "En el navegador, pulse <b>Activar notificaciones</b> en la franja inferior si desea recibir avisos.",
    ]:
        y = bullet(c, item, 62, y, PAGE_W - 124)
    c.showPage()


def final_page(c: canvas.Canvas) -> None:
    page_title(c, "8", "Acceso, disponibilidad y ayuda", 9)
    y = PAGE_H - 115
    y = p(c, "D&oacute;nde usar Gestinem", 58, y, PAGE_W - 116, HEADING) - 4
    y = bullet(
        c,
        f'<b>Navegador:</b> <link href="{WEB_URL}" color="#004B76"><u>{WEB_URL}</u></link>.',
        62,
        y,
        PAGE_W - 124,
    )
    y = bullet(
        c,
        f'<b>Android:</b> <link href="{ANDROID_URL}" color="#004B76"><u>Gestinem Chat en Google Play</u></link>.',
        62,
        y,
        PAGE_W - 124,
    )
    y = bullet(
        c,
        "<b>iPhone y iPad:</b> la versi&oacute;n para Apple contin&uacute;a en revisi&oacute;n. Hasta su publicaci&oacute;n, utilice el navegador.",
        62,
        y,
        PAGE_W - 124,
    )
    y -= 22
    y = p(c, "Seguridad", 58, y, PAGE_W - 116, HEADING) - 4
    for item in [
        "Cierre la sesi&oacute;n en equipos compartidos desde el men&uacute; o desde Mi &aacute;rea.",
        "No comparta la contrase&ntilde;a ni los enlaces de activaci&oacute;n o recuperaci&oacute;n.",
        "Los documentos y adjuntos pueden tener disponibilidad limitada. Desc&aacute;rguelos cuando los necesite conservar.",
        "Si cambia de tel&eacute;fono o navegador, vuelva a entrar con el mismo correo y contrase&ntilde;a.",
    ]:
        y = bullet(c, item, 62, y, PAGE_W - 124)
    y -= 20
    y = box(
        c,
        58,
        y,
        PAGE_W - 116,
        "<b>&iquest;Necesita ayuda?</b> Si el enlace de invitaci&oacute;n ha caducado, no recibe los correos o no puede acceder, contacte con el despacho por los medios habituales para que Gestinem revise su acceso.",
    )
    y -= 30
    p(
        c,
        "Este manual refleja la interfaz de cliente incluida en la versi&oacute;n publicada en octubre de 2026. Algunas opciones, como Facturaci&oacute;n o Ayudas y subvenciones, solo aparecen cuando el despacho las ha habilitado.",
        58,
        y,
        PAGE_W - 116,
        SMALL,
    )
    c.showPage()


def build() -> None:
    missing = [path for path in [LOGO] if not path.exists()]
    required = [
        ASSETS / "01_conversacion.png",
        ASSETS / "02_menu.png",
        ASSETS / "03_adjuntar.png",
        ASSETS / "04_acciones_mensaje.png",
        ASSETS / "05_documentacion.png",
        ASSETS / "06_mi_area.png",
    ]
    missing.extend(path for path in required if not path.exists())
    if missing:
        raise FileNotFoundError("Faltan recursos: " + ", ".join(str(path) for path in missing))

    c = canvas.Canvas(str(OUTPUT), pagesize=A4, pageCompression=1)
    c.setTitle("Gestinem - Manual de uso para clientes")
    c.setAuthor("Gestinem")
    c.setSubject("Uso de Gestinem Chat para clientes")

    cover(c)
    activation(c)
    screenshot_page(
        c,
        page=3,
        number="2",
        title="La pantalla principal es el chat",
        image="01_conversacion.png",
        intro="Al entrar como cliente no aparece una bandeja separada. La aplicaci&oacute;n abre directamente la conversaci&oacute;n y mantiene los dos canales en la parte superior.",
        sections=[
            (
                "Canal general y Tu asesor",
                [
                    "Pulse la tarjeta superior para cambiar de canal.",
                    "El punto rojo indica que hay mensajes pendientes en ese canal.",
                    "La conversaci&oacute;n elegida se muestra debajo sin abandonar la pantalla.",
                ],
            ),
            (
                "Mensajes",
                [
                    "Los mensajes del despacho aparecen a la izquierda y los suyos a la derecha.",
                    "La franja azul recuerda que puede pulsar un mensaje para responder o reaccionar.",
                    "El campo para escribir y los botones de voz, adjuntos y env&iacute;o est&aacute;n siempre al pie del chat.",
                ],
            ),
        ],
    )
    screenshot_page(
        c,
        page=4,
        number="3",
        title="Escriba, adjunte y env&iacute;e",
        image="03_adjuntar.png",
        intro="Escriba en <b>Escribe un mensaje...</b> y pulse el bot&oacute;n azul de enviar. En pantallas estrechas, el bot&oacute;n <b>+</b> re&uacute;ne las opciones adicionales.",
        sections=[
            (
                "Documento o imagen",
                [
                    "Permite adjuntar PDF, im&aacute;genes, Word, Excel, texto, XML, CSV o ZIP.",
                    "Cada archivo puede ocupar hasta 50 MB.",
                    "Los nombres claros facilitan que el despacho identifique el documento.",
                ],
            ),
            (
                "Contacto, emoticonos y voz",
                [
                    "Contacto comparte nombre, tel&eacute;fono o correo.",
                    "El icono de la cara abre el selector de emoticonos cuando se muestra fuera del men&uacute;.",
                    "El micr&oacute;fono inicia una nota de voz; podr&aacute; cancelarla o enviarla al terminar.",
                ],
            ),
        ],
    )
    screenshot_page(
        c,
        page=5,
        number="4",
        title="Responda y gestione mensajes",
        image="04_acciones_mensaje.png",
        intro="Pulse o mantenga pulsado un mensaje para abrir sus acciones. El men&uacute; aparece desde la parte inferior, exactamente como en la aplicaci&oacute;n.",
        sections=[
            (
                "Acciones disponibles",
                [
                    "Pulse un emoticono para reaccionar; vuelva a pulsarlo para retirar su reacci&oacute;n.",
                    "Responder incluye una referencia al mensaje original.",
                    "Puede editar sus mensajes propios de texto.",
                    "Puede eliminar un mensaje propio si no contiene adjuntos.",
                ],
            ),
            (
                "Adjuntos",
                [
                    "Pulse un adjunto para descargarlo cuando est&eacute; disponible.",
                    "La aplicaci&oacute;n muestra si el archivo ha caducado o si ya no puede descargarse.",
                ],
            ),
        ],
    )
    screenshot_page(
        c,
        page=6,
        number="5",
        title="Abra las funciones desde el men&uacute;",
        image="02_menu.png",
        intro="Pulse el icono de tres l&iacute;neas de la esquina superior izquierda. El men&uacute; muestra su nombre y correo y concentra todos los accesos.",
        sections=[
            (
                "Opciones del cliente",
                [
                    "Conversaciones vuelve al chat.",
                    "Documentaci&oacute;n abre documentos y certificados.",
                    "Facturaci&oacute;n y Ayudas y subvenciones aparecen solo si el despacho las ha habilitado.",
                    "Mi &aacute;rea contiene sus datos y los de la empresa.",
                    "Manual de Gestinem abre siempre la versi&oacute;n publicada del PDF.",
                    "Cerrar sesi&oacute;n aparece como &uacute;ltima opci&oacute;n.",
                ],
            ),
        ],
    )
    screenshot_page(
        c,
        page=7,
        number="6",
        title="Consulte documentos y certificados",
        image="05_documentacion.png",
        intro="Documentaci&oacute;n agrupa los archivos compartidos por el despacho y las solicitudes de certificados oficiales.",
        sections=[
            (
                "Mis documentos",
                [
                    "Consulte facturas, certificados, n&oacute;minas, impuestos y otros archivos publicados para su empresa.",
                    "Pulse un documento para revisar sus datos, previsualizarlo y descargarlo cuando est&eacute; disponible.",
                ],
            ),
            (
                "Solicitar certificados",
                [
                    "El estado superior confirma si el certificado digital est&aacute; preparado por el despacho.",
                    "Seleccione el tipo disponible y revise el estado de cada solicitud.",
                    "Una opci&oacute;n bloqueada indica que el despacho todav&iacute;a no ha habilitado esa funci&oacute;n.",
                ],
            ),
        ],
    )
    screenshot_page(
        c,
        page=8,
        number="7",
        title="Revise Mi &aacute;rea",
        image="06_mi_area.png",
        intro="Mi &aacute;rea muestra el usuario conectado, los datos de la empresa y las solicitudes de modificaci&oacute;n enviadas al despacho.",
        sections=[
            (
                "Datos y solicitudes",
                [
                    "Compruebe nombre, correo de acceso, NIF/CIF, direcci&oacute;n, localidad, tel&eacute;fono y correo de la empresa.",
                    "Pulse <b>Solicitar modificaci&oacute;n</b> para proponer cambios en los datos o el logotipo.",
                    "El despacho revisa la solicitud antes de aplicar los cambios.",
                ],
            ),
            (
                "Opciones de la cuenta",
                [
                    "Enviar con Intro cambia el comportamiento del teclado.",
                    "Desde esta pantalla puede consultar la privacidad, solicitar la eliminaci&oacute;n de la cuenta y cerrar sesi&oacute;n.",
                ],
            ),
        ],
    )
    final_page(c)
    c.save()


if __name__ == "__main__":
    build()
