# Namespace y version verificados contra el XSD oficial publicado en
# https://www.facturae.gob.es (Facturaev3_2_1.xml) y contra una factura real
# aceptada por FACe (ver services/facturae/schemas/ y el skill facturae-xml).
FACTURAE_NS = "http://www.facturae.es/Facturae/2014/v3.2.1/Facturae"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"

SCHEMA_VERSION = "3.2.1"
MODALITY_INDIVIDUAL = "I"
INVOICE_ISSUER_TYPE = "EM"
INVOICE_DOCUMENT_TYPE = "FC"
INVOICE_CLASS_ORIGINAL = "OO"
INVOICE_CLASS_CORRECTIVE = "OR"

TAX_TYPE_VAT = "01"
TAX_TYPE_IRPF = "04"

UNIT_OF_MEASURE_UNITS = "01"

ADMIN_CENTRE_ROLE_OFFICE = "01"
ADMIN_CENTRE_ROLE_MANAGER = "02"
ADMIN_CENTRE_ROLE_PROCESSING = "03"
ADMIN_CENTRE_ROLE_PROPONENT = "04"

FACTURAE_STATUS_NO_GENERADO = "no_generado"
FACTURAE_STATUS_GENERADO = "generado"
FACTURAE_STATUS_ERROR_VALIDACION = "error_validacion"
FACTURAE_STATUS_FIRMADO = "firmado"
FACTURAE_STATUS_PRESENTADO = "presentado"
