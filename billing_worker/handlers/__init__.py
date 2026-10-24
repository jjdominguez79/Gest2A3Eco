"""Manejadores de trabajo de billing_worker, uno por tipo de trabajo.

render_pdf, publish_document, send_email y send_notification corresponden a
los tipos de trabajo descritos en la seccion 10 del encargo. publish_document,
send_email y send_notification son llamadas HTTP puras contra el backend (la
logica vive alli, ya probada); render_pdf es el unico que ejecuta trabajo
local (plantilla + Chromium/Playwright, ver Etapa 6).
"""
