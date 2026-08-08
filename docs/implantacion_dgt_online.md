# Implantacion de Tramites DGT online

## Estado de las fases

- Fase 0: `main` integrado en `feature/modulo-tramites-dgt`.
- Fase 1: API FastAPI, modelo relacional, migracion PostgreSQL, tokens,
  caducidad, revocacion, auditoria y autenticacion interna.
- Fase 2: portal responsive por rol, autoguardado, revision, privacidad y
  carga privada validada.
- Fase 3: `ApiDgtRepository`, configuracion externa, enlaces HTTPS, copia,
  email, WhatsApp, refresco, estados separados y descarga bajo demanda.
- Fase 4: pendiente de plantillas legales definitivas y seleccion/credenciales
  del proveedor de firma.
- Fase 5: imagen Docker y CI preparadas. El despliegue real queda pendiente de
  la suscripcion Azure/Supabase, DNS, certificados y secretos de produccion.

## Puesta en marcha local

```powershell
pip install -r backend/requirements.txt
$env:DGT_INTERNAL_API_KEY = "secreto-local"
$env:DGT_PUBLIC_BASE_URL = "http://localhost:8000"
uvicorn backend.dgt_api.app:app --reload
```

En `config.local.json` de Gest2A3Eco:

```json
{
  "dgt_api_url": "http://localhost:8000",
  "dgt_api_key": "secreto-local"
}
```

Sin esas dos opciones, el modulo DGT no queda operativo desde la aplicacion
de escritorio. No existe fallback a base local.

## Produccion

1. Crear PostgreSQL y ejecutar `backend/migrations/001_initial.sql`.
2. Sustituir el almacenamiento de desarrollo por un volumen cifrado o un
   adaptador de bucket privado antes de escalar a mas de una instancia.
3. Configurar las variables de `backend/.env.example` como secretos del
   servicio, nunca en Git.
4. Construir `backend/Dockerfile` y desplegarlo detras de HTTPS.
5. Configurar `tramites.gestinem.es` y verificar `/health`, `/docs` y un flujo
   completo de vendedor/comprador en el entorno de pruebas.
6. Definir retencion, copias, restauracion y borrado de documentos conforme a
   la politica de proteccion de datos de Gestinem.

## Verificacion ejecutada

Las pruebas focalizadas DGT pasan (`12 passed`). La suite amplia alcanza
`254 passed` y conserva cuatro fallos ajenos a DGT en maestro contable,
maestro de terceros y OCR. No se modificaron esos modulos por estar fuera del
alcance expresamente fijado para esta rama.
