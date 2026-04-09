# Arquitectura inicial de GestinemAppFull

## Vision del sistema

GestinemAppFull nace como la evolucion web de Gest2A3Eco para el trabajo diario del despacho y, en fases posteriores, para el acceso controlado de clientes. El objetivo no es replicar literalmente la aplicacion desktop, sino construir una plataforma multiempresa y multiusuario centrada en operativa documental-contable, trazabilidad y escalabilidad.

La primera base tecnica se plantea como:

- backend monolitico modular en FastAPI
- PostgreSQL como base de datos principal
- Flutter Web como cliente de escritorio
- almacenamiento documental centralizado
- procesos asincronos para OCR, clasificacion y sincronizaciones futuras
- integracion con A3 desacoplada mediante conector local

## Modulos principales

### Dashboard

- vista de entrada por empresa activa
- resumen de estados operativos
- accesos rapidos a bandejas y procesos pendientes

### Facturacion

- emision y consulta de facturas
- estados de generacion y exportacion
- base preparada para portal cliente

### Documentacion

- entrada documental centralizada
- bandejas por estado
- filtros, validacion y trazabilidad

### OCR y revision

- extraccion de texto
- clasificacion automatica
- revision humana y correccion de campos

### Contabilizacion

- cola de documentos pendientes de contabilizar
- generacion de lotes para suenlace
- base para asientos y conciliacion futura

### Plan contable

- catalogo contable especifico por empresa
- sincronizacion posterior con A3

### Extractos

- importacion de extractos bancarios
- normalizacion y preparacion de contabilizacion

## Concepto de empresa activa

La aplicacion opera siempre con una empresa activa en contexto. El usuario podra cambiar de empresa desde el shell principal, pero el dashboard, las bandejas y los procesos se cargaran sobre una empresa seleccionada.

Esto permite:

- aislar operativa diaria por empresa
- mantener configuraciones y permisos por empresa
- compartir componentes de interfaz y servicios sin mezclar datos

## Terceros globales vs plan contable por empresa

El sistema debe separar dos conceptos:

- terceros globales: entidades maestras compartidas entre empresas del despacho
- plan contable por empresa: cuentas, subcuentas y configuraciones contables propias de cada empresa

Esta separacion evita duplicar terceros y permite que una misma entidad tenga distinta asignacion contable segun la empresa activa.

## Flujo documental completo

El flujo documental objetivo del sistema es:

`entradas -> clasificacion -> OCR -> pendiente_contabilizar -> suenlace -> contabilizadas`

Interpretacion operativa:

- `entradas`: documentos recien incorporados al sistema
- `clasificacion`: asignacion automatica o manual de categoria
- `OCR`: extraccion y correccion de texto/campos
- `pendiente_contabilizar`: documentos validados y listos para tratamiento contable
- `suenlace`: lote preparado o exportado para integracion con A3
- `contabilizadas`: documento ya tratado y cerrado operativamente

## Estrategia de integracion con A3

La integracion con A3 no debe depender del frontend ni de acceso directo desde navegador a carpetas o binarios locales. La estrategia base es:

- backend central publica trabajos de sincronizacion o exportacion
- un conector local Windows, instalado en el entorno del despacho con acceso real a A3, consume esos trabajos
- el conector ejecuta importaciones/exportaciones y devuelve resultado, trazas y artefactos

Esto permite mantener:

- compatibilidad con instalaciones locales de A3
- aislamiento de seguridad
- evolucion futura sin acoplar la plataforma web al escritorio

## Fases de desarrollo

### Fase 0. Base tecnica

- scaffold backend FastAPI
- scaffold frontend Flutter Web
- modelo de shell de escritorio
- documento de arquitectura y estructura modular

### Fase 1. Nucleo interno

- autenticacion
- seleccion de empresa activa
- dashboard inicial
- gestion de usuarios y permisos
- catalogo de empresas

### Fase 2. Datos maestros

- terceros globales
- plan contable por empresa
- configuraciones base por empresa

### Fase 3. Documental y OCR

- subida documental
- bandejas por estado
- OCR y revision
- trazabilidad de cambios

### Fase 4. Contabilizacion y suenlace

- documentos pendientes
- lotes de exportacion
- control de estado contable

### Fase 5. Facturacion y extractos

- emision web
- importacion bancaria
- conciliacion y apoyo a contabilizacion

### Fase 6. Integracion A3 y portal cliente

- conector local A3
- sincronizacion de catalogos
- acceso cliente para documentacion y facturacion
