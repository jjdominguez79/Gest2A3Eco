# Plan historico de implantacion del modulo OCR

**Inicio del plan:** 2026-06-09.

**Estado revisado:** 2026-08-15.

**Nota:** este documento conserva la evolucion del modulo. La descripcion
operativa vigente esta en [`ocr_estado_actual.md`](ocr_estado_actual.md).

## Objetivo original

Importar facturas recibidas en PDF o imagen, extraer datos fiscales, revisarlos,
validarlos y proyectarlos al flujo contable que genera `suenlace.dat`, con
trazabilidad de las correcciones manuales.

## Arquitectura alcanzada

```text
Documento
  -> OcrService
       |-- BackendOcrEngine -> FastAPI -> Azure
       |-- AzureInvoiceEngine local de compatibilidad
       |-- PdfTextEngine
       `-- LocalOcrEngine / Tesseract
  -> tablas OCR tipadas
  -> revision y validacion
  -> OcrContabilidadService
  -> facturas_recibidas_docs
  -> Contabilidad -> suenlace.dat
```

## Fases completadas

### Fases 1 y 2 — prototipo y enriquecimiento, retiradas

- Primera captura OCR y generacion contable mediante tablas legacy.
- Incorporacion de retenciones, subcuentas y resolucion de terceros por NIF.
- Sustitucion posterior de pantallas y servicios legacy por el nucleo tipado.

### Fase 3 — nucleo OCR tipado

- `OcrInvoiceResult`, lineas de IVA, retenciones y estados tipados.
- Motores desacoplados mediante `OcrEngineBase`.
- Interpretacion de texto, hash, duplicados, persistencia y auditoria.
- Pantalla unificada de captura y revision.
- Tablas `documentos_ocr`, `facturas_recibidas_ocr`, detalles fiscales y
  `ocr_correcciones`.

### Fase 4 — extraccion y normalizacion

- Deteccion de NIF, razon social, numero, fechas, importes y tablas de IVA.
- Normalizacion de importes europeos/internacionales y fechas habituales.
- Preferencia del NIF emisor frente al NIF del cliente en cabeceras conocidas.
- Pruebas unitarias de interpretacion, layouts PDF y normalizacion Azure.

### Fase 5 — motores local y Azure

- Motor Tesseract implementado y opcional; su disponibilidad depende de la
  instalacion del ejecutable y del idioma en cada puesto.
- SDK Azure incluido en dependencias y mapeo del modelo generico y personalizado.
- OCR Azure delegado al backend mediante `WorkstationToken`.
- Claves Azure retiradas de la configuracion persistida del escritorio.

### Fase 6 — aprendizaje asistido

- Registro privado de facturas validadas y datos estructurados.
- Tabla `ocr_aprendizaje_ejemplos`.
- Exportacion a Azure Blob para preparar conjuntos de entrenamiento.

El entrenamiento y la publicacion de modelos siguen siendo tareas controladas
en Azure Studio; las correcciones no modifican automaticamente el modelo.

## Trabajo pendiente

- Medir precision por proveedor, tipo de documento, motor y campo.
- Ampliar la extraccion de lineas de articulo y monedas cuando el flujo contable
  necesite ese detalle.
- Mejorar el preprocesado local de escaneos y documentar una instalacion
  reproducible de Tesseract para produccion.
- Incorporar una UI de seleccion/promocion de modelos con rollback controlado.
- Automatizar un conjunto anonimizado de regresion con documentos reales.

## Criterios de aceptacion vigentes

- El archivo original se archiva en el repositorio compartido y los duplicados
  se detectan por hash.
- El OCR produce una propuesta revisable; nunca contabiliza silenciosamente.
- Cabecera, IVA y retenciones se pueden corregir y quedan auditados.
- Una factura validada se proyecta a Contabilidad sin generar directamente el
  enlace A3 desde la pantalla OCR.
- El backend mantiene las credenciales Azure fuera de los puestos.
- Un error Azure seleccionado queda visible y no se oculta con datos locales.
- La exportacion A3 sigue usando los renderizadores y procesos contables
  compartidos.

## Riesgos permanentes

| Riesgo | Mitigacion |
|---|---|
| Escaneos de baja calidad | Azure o Tesseract y revision manual |
| Formatos fiscales no estandar | Validacion de totales y editor de detalle |
| Confusion emisor/receptor | Reglas de cabecera, maestro de terceros y revision |
| Degradacion de un modelo personalizado | Muestra de control y rollback del ID |
| Exposicion de documentos de entrenamiento | Contenedor privado y acceso limitado |
| Regresion en `suenlace.dat` | Proyeccion contable unica y pruebas de renderizado |
