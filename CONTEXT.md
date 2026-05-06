# CONTEXT

## Resumen ejecutivo
- Gest2A3Eco es una app de escritorio en Python/Tkinter para gestionar empresas, plantillas, facturas emitidas e importaciones orientadas a A3ECO.
- Punto de entrada: `main.py`. La aplicacion arranca en el panel general, desde donde se entra al listado de empresas y al dashboard de cada empresa.
- Persistencia principal: SQLite en `plantillas/gest2a3eco.db` mediante `models/gestor_sqlite.py`. `models/gestor_plantillas.py` queda como compatibilidad/semilla, no como flujo principal.

## Modulos activos
- `views/ui_panel_general.py`: panel principal y listado de empresas.
- `views/ui_dashboard_empresa.py`: acceso a modulos de la empresa.
- `views/ui_empresa_dialog.py`: configuracion de empresa, terceros asignados y plan contable.
- `views/ui_plantillas.py`: gestion de plantillas de bancos, facturas emitidas y facturas recibidas.
- `views/ui_procesos.py`: importaciones desde Excel y generacion de `suenlace.dat`.
- `views/ui_facturas_emitidas.py`: facturas emitidas, PDF, envio por email y generacion de suenlace.

## Arquitectura
- UI: `views/ui_*.py`
- Controladores: `controllers/*.py`
- Datos: `models/gestor_sqlite.py`
- Procesos A3: `procesos/bancos.py`, `procesos/facturas_emitidas.py`, `procesos/facturas_recibidas.py`
- Servicios auxiliares: `services/*.py`

## Flujo real
- `python main.py` abre el panel general.
- Desde el listado de empresas se crea, edita, copia o elimina empresa, y se entra al dashboard.
- Desde el dashboard se accede a:
  - `Plantillas`
  - `Facturas emitidas`
  - `Importaciones`
  - `Configuracion de empresa`

## Reglas relevantes
- `digitos_plan` se respeta en cuentas y subcuentas.
- La gestion de terceros vive en la configuracion de empresa, no como modulo separado en facturas.
- El ejercicio visible en listados debe interpretarse como ultimo ejercicio abierto, no como unico ejercicio posible de la empresa.
- La generacion masiva de suenlace en facturas emitidas usa marcado explicito de facturas.

## Estado actual
- El flujo antiguo de seleccion de empresa independiente y el modulo documental se han retirado.
- No existe vista dedicada de centro contable; esa informacion se integra en dashboard/configuracion.
- No hay UI especifica para facturas recibidas; su tratamiento operativo sigue en importaciones.
- Hay cambios locales sin commitear en el repositorio; no revertirlos automaticamente.

## Verificacion manual minima
- Abrir `python main.py`.
- Crear o editar una empresa y comprobar persistencia en SQLite.
- Crear plantilla y reabrirla.
- Importar un Excel de prueba y generar `suenlace.dat`.
- Crear una factura emitida, generar PDF y suenlace, y comprobar que el marcado/estado se actualiza.
