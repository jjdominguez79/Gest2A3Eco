# Gest2A3Eco

Aplicacion de escritorio en Python/Tkinter para Windows orientada a gestion
contable de Gestinem.

Funciones principales:

- Generacion de `suenlace.dat` para A3ECO.
- Gestion de facturas emitidas y recibidas.
- Generacion de PDF desde plantillas Word.
- OCR de facturas recibidas.
- Comunicaciones, notificaciones, firma documental y tramites DGT.

## Requisitos

- Python 3.10+
- Windows
- PostgreSQL accesible desde todos los puestos
- Dependencias de `requirements.txt`

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Ejecucion

```bash
python main.py
```

La conexion de datos se configura con `postgres_dsn` en `config.local.json` o
con la variable `GEST2A3ECO_POSTGRES_DSN`.

## Compilacion

```bash
pyinstaller Gest2A3Eco.spec
```

La build empaqueta recursos de aplicacion como `logo.png`, `icono.ico`,
`assets/`, `plantillas/email_factura.html` y `config.example.json`. No debe
incluir datos reales, configuracion local ni documentos generados.

## Arquitectura

```text
main.py                     Punto de entrada
controllers/                Coordinacion y validacion
views/                      Pantallas Tkinter
procesos/                   Generadores A3ECO y PDF
models/                     Gestor PostgreSQL y renderizadores A3ECO
services/                   Auth, email, OCR, notificaciones, integraciones
utils/                      Configuracion, validaciones y formato
plantillas/                 Plantillas versionables
assets/                     Recursos graficos
```

## Datos

PostgreSQL es la unica base operativa. No hay flujo soportado con bases locales
en fichero. El gestor PostgreSQL inicializa el esquema si la base esta vacia y
aplica comprobaciones aditivas necesarias al arrancar.

Los documentos generados se almacenan en rutas compartidas de red configuradas
para que todos los equipos trabajen sobre la misma informacion.

## Convenciones

- UI en `views/`.
- Logica de negocio en `controllers/`, `services/` o `procesos/`.
- Persistencia en `models/gestor_postgres.py`.
- Los PDFs se generan siempre con `procesos/facturas_word.py`.
- La carpeta A3ECO solo recibe PDFs durante la generacion de `suenlace.dat`.
