"""Worker cloud independiente para facturacion autonoma de clientes.

Procesa el pipeline fiscal/PDF/entrega de ``ClientInvoiceProcessingQueue``
(render_pdf, publish_document, send_email, send_notification y, desde la
Etapa 7, fiscal_registration/fiscal_cancellation). Reside en un servicio
Railway independiente del backend, sin acceso a Tkinter, pywin32, Word COM,
el PostgreSQL interno del escritorio, el NAS ni rutas UNC. Ver
docs/adr/0001-facturacion-autonoma-cliente.md.
"""
