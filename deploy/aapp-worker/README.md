# Worker AAPP

Ejecuta en Synology las solicitudes AEAT/TGSS creadas por el escritorio o por
Flutter. El PFX se descarga solo despues de reclamar una solicitud, se escribe
en un directorio temporal en memoria y desaparece al finalizar el tramite.

## Preparacion del piloto

1. Crear `secrets/aapp_worker_api_key.txt` con un secreto aleatorio largo.
2. Configurar el mismo valor como `AAPP_WORKER_API_KEY` en el backend.
3. Configurar en el backend la clave `CLIENT_CERTIFICATES_MASTER_KEY`, el
   contenedor Azure privado y `CLIENT_CERTIFICATES_ENABLED=true`.
4. Desde el escritorio, abrir el certificado de la empresa piloto y pulsar
   **Preparar para app / worker**.
5. Activar Documentos y Solicitud de certificados solo para esa empresa.
6. Arrancar con `docker compose up -d --build` desde este directorio.

Para la primera calibracion puede usarse `AAPP_HEADLESS=false` en un equipo con
interfaz grafica. En Synology debe mantenerse `true`; las capturas de diagnostico
se escriben en el volumen configurado sin incluir el PFX ni la contrasena.
