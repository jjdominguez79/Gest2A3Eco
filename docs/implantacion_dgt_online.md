# Implantacion de Tramites DGT online

**Estado del codigo:** modulo integrado con backend FastAPI, portal publico,
persistencia PostgreSQL, Dataprius y firma.

**Ultima revision:** 2026-08-15.

La URL de Railway incluida en la configuracion de nuevas instalaciones es un
valor predeterminado del repositorio; esta guia no certifica por si sola la
disponibilidad del servicio externo.

## Capacidades actuales

- Expedientes con partes vendedor/comprador, vehiculo y operacion.
- Enlaces por rol con caducidad, revocacion y regeneracion independiente.
- Portal responsive, autoguardado, envio, subsanaciones y modo solo lectura al
  finalizar.
- Documentos privados validados y archivo en Dataprius por expediente.
- Estados y evidencias de firma mediante SignRequest.
- Auditoria de eventos, control de versiones y eliminacion controlada.
- Vinculo `dgt_facturas` en la PostgreSQL principal cuando un expediente genera
  una factura local.

Siguen dependiendo de decisiones operativas las plantillas legales definitivas,
las politicas de retencion y copias, y la supervision de proveedores externos.

## Desarrollo local

```powershell
python -m pip install -r backend/requirements.txt
$env:DGT_DATABASE_URL = "postgresql+psycopg://usuario:password@localhost:5432/dgt"
$env:DGT_INTERNAL_API_KEY = "secreto-interno-local"
$env:DGT_PUBLIC_BASE_URL = "http://localhost:8000"
python -m uvicorn backend.api.app:app --reload
```

Crear un puesto de desarrollo con la clave interna:

```text
POST /api/v1/admin/workstations
X-API-Key: <DGT_INTERNAL_API_KEY>
{"name": "PC-DESARROLLO"}
```

Provisionar el token devuelto en Windows Credential Manager:

```powershell
python -m utils.provision_workstation --only-token
```

Configuracion no sensible del escritorio:

```json
{
  "integrations_api_url": "http://localhost:8000"
}
```

`DGT_INTERNAL_API_KEY` nunca se instala en el escritorio. Las claves legacy
`integrations_api_key` y `dgt_api_key` no autentican este flujo. Sin URL y
`WorkstationToken`, el modulo remoto no esta operativo; no existe fallback a
una base local.

## Produccion

1. Configurar `DGT_DATABASE_URL` en Railway y aplicar
   `backend/migrations/001_initial.sql` sobre una base vacia.
2. Configurar `DGT_INTERNAL_API_KEY`, URL publica, SignRequest, Dataprius y los
   restantes secretos descritos en
   [`security/secrets-architecture.md`](security/secrets-architecture.md).
3. Construir `backend/Dockerfile` y desplegar detras de HTTPS.
4. Verificar `/health`, `/docs`, autenticacion de un puesto y un flujo completo
   de vendedor/comprador en un entorno de prueba.
5. Probar carga, descarga, firma, subsanacion, finalizacion y borrado conforme a
   la politica de proteccion de datos.
6. Definir monitorizacion, copias, restauracion y retencion antes de considerar
   el servicio operativo.

## Almacenamiento

- Expedientes, enlaces, auditoria y metadatos viven en la PostgreSQL del
  backend.
- Los documentos aportados se suben a Dataprius bajo la carpeta del expediente
  y sus metadatos quedan en `dgt_documentos.dataprius_json`.
- El backend puede mantener una copia privada tecnica para descarga y control;
  `DGT_STORAGE_DIR` es solo la opcion local de desarrollo.
- Los documentos generados desde el escritorio se registran por el endpoint de
  documentos generados y se archivan cuando la integracion esta disponible.
- La base principal del escritorio no replica expedientes; conserva solo el
  vinculo contable necesario.

## Verificacion

Ejecutar desde la raiz:

```powershell
$env:PYTHONPATH = "."
python -m pytest tests/test_dgt_api.py tests/test_dgt_postgres_migration.py tests/test_ui_tramites_dgt.py -q
```

La suite completa se recopila con `python -m pytest --collect-only -q`. No deben
mantenerse cifras historicas de pruebas como garantia permanente; el resultado
valido es el de la revision ejecutada sobre el commit que se va a desplegar.
