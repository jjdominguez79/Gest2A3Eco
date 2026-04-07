# Modulo Documentos

## Estructura

El MVP documental queda integrado en el bloque de contabilidad de Gest2A3Eco como una nueva pestaña `Documentos`.

- `views/ui_documentos.py`
  Vista principal del modulo. Incluye:
  - listado de plantillas
  - asistente de generacion por pestañas
  - historico documental
  - gestion de intervinientes habituales
- `controllers/ui_documentos_controller.py`
  Orquesta la UI, valida el flujo y reutiliza el gestor SQLite existente.
- `services/documentos_service.py`
  Encapsula:
  - creacion de plantillas de ejemplo
  - deteccion de variables `{{ variable }}`
  - composicion de contexto
  - generacion DOCX
  - conversion PDF desacoplada
- `models/gestor_sqlite.py`
  Amplia el esquema y añade CRUD para plantillas documentales, intervinientes, operaciones e historico.

## Tablas nuevas

Se han añadido estas tablas:

- `plantillas_documentos`
  Registro de plantillas DOCX por empresa y ejercicio.
- `intervinientes`
  Personas o entidades reutilizables en documentos.
- `documentos_generados`
  Historico documental con rutas de salida y JSON del borrador usado.
- `documento_intervinientes`
  Relacion entre documento generado e intervinientes usados.
- `operaciones`
  Base para futuras agrupaciones documentales por operacion.
- `operacion_intervinientes`
  Relacion entre operaciones e intervinientes.

## Flujo de generacion

1. El modulo asegura tres plantillas de ejemplo en la carpeta de plantillas Word.
2. Se detectan automaticamente las variables presentes en cada DOCX con el patron `{{ variable }}`.
3. El usuario elige plantilla.
4. El usuario carga un cliente existente o introduce datos manuales.
5. El usuario añade intervinientes habituales o manuales.
6. Se genera un DOCX final en la ruta configurada.
7. Si el entorno permite conversión, se intenta generar PDF.
8. Se guarda un registro en `documentos_generados` y se conserva el JSON del asistente para reabrir o duplicar.

## Como crear nuevas plantillas

1. Preparar un `.docx`.
2. Añadir variables con formato `{{ cliente.nombre_razon_social }}`.
3. Importar la plantilla desde la pestaña `Plantillas`.
4. Usar `Releer variables` si se cambia el archivo.

## Convencion de variables

Variables recomendadas del MVP:

- `{{ fecha_hoy }}`
- `{{ empresa.nombre }}`
- `{{ empresa.cif }}`
- `{{ cliente.nombre_razon_social }}`
- `{{ cliente.nif }}`
- `{{ cliente.domicilio }}`
- `{{ cliente.cp }}`
- `{{ cliente.municipio }}`
- `{{ cliente.provincia }}`
- `{{ documento.titulo_documento }}`
- `{{ documento.observaciones }}`
- `{{ operacion.titulo }}`
- `{{ intervinientes_resumen }}`

## Rutas de salida

La salida documental se controla desde `config.json`:

- `documentos_output_dir`
  Carpeta raiz de salida.
- `documentos_output_structure`
  Valores soportados:
  - `cliente`
  - `operacion`
  - `tipo_documento`

Si no se define, el modulo usa `documentos_generados/<empresa>/<cliente>`.

## Limitaciones actuales

- La sustitucion DOCX es simple y trabaja bien con variables escritas en un mismo bloque de texto.
- No hay aun clausulas condicionales ni bucles avanzados.
- La gestion de operaciones existe a nivel de datos pero no tiene UI completa en este MVP.
- La conversion PDF depende de que el entorno permita `docx2pdf` y Word instalado.

## Proximos pasos recomendados

- Añadir UI completa para operaciones.
- Incorporar clausulas condicionales.
- Permitir generacion multiple de documentos.
- Añadir firma documental.
- Mejorar el motor de plantillas para escenarios complejos.
