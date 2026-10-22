# Worker AAPP

Ejecuta en Synology dos procesos aislados: uno para las solicitudes de
certificados AEAT/TGSS y otro para las consultas DEHu/DGT-DEV. El PFX se
descarga solo despues de reclamar una solicitud, se escribe en un directorio
temporal en memoria y desaparece al finalizar el tramite.

## Preparacion del piloto

1. Crear `secrets/aapp_certificates_worker_api_key.txt` y
   `secrets/aapp_notifications_worker_api_key.txt` con dos secretos aleatorios
   largos y diferentes.
2. Configurar esos valores como `AAPP_CERTIFICATES_WORKER_API_KEY` y
   `AAPP_NOTIFICATIONS_WORKER_API_KEY` en el backend.
3. Configurar en el backend la clave `CLIENT_CERTIFICATES_MASTER_KEY`, el
   contenedor Azure privado y `CLIENT_CERTIFICATES_ENABLED=true`.
4. Desde el escritorio, abrir el certificado de la empresa piloto y pulsar
   **Preparar para app / worker**.
5. Activar Documentos y Solicitud de certificados solo para esa empresa.
6. Arrancar ambos procesos con `docker compose up -d --build` desde este
   directorio.

Para la primera calibracion puede usarse `AAPP_HEADLESS=false` en un equipo con
interfaz grafica. En Synology debe mantenerse `true`; las capturas de diagnostico
se escriben en el volumen configurado sin incluir el PFX ni la contrasena.
