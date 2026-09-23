# Gest2A3Eco AAPP worker

Worker aislado para procesar en Synology las solicitudes de certificados AEAT
y TGSS creadas desde el escritorio o Flutter.

La version 2026.09.18.2 ofrece tambien el certificado digital al origen exacto
`https://ipce.seg-social.es`, utilizado por el login del tramite TGSS. Es
necesario reconstruir la imagen; reiniciar el contenedor no incorpora el cambio.

La version 2026.09.18.3 captura el PDF del boton final TGSS `SPM.ACC.IMPRIMIR`,
tanto en descarga como en respuesta PDF o pestana nueva. Solo pulsa una vez.
El diagnostico omite sesiones y tickets de las URL y prioriza controles no ocultos.

La version 2026.09.18.4 distingue el PDF resguardo AEAT del certificado final
mediante pypdf y conserva los dos documentos con identidades independientes.
Usa el protocolo de cola 3: el backend rechaza workers anteriores para evitar
que una comprobacion de expediente se convierta en una nueva solicitud.
El backend necesita la migracion 026_aeat_certificate_followup.sql. Desplegar
backend y worker conjuntamente (y despues Flutter); no reiniciar una imagen vieja.

Los resguardos de AEAT_CORRIENTE con referencia verificable se consultan cada
24 horas. Tras 72 horas se avisa del retraso y se sigue consultando diariamente;
el plazo no implica certificado negativo. Otros tramites, PDF sin texto,
referencias ambiguas o pantallas no reconocidas requieren revision y no se
vuelven a presentar. La recogida usa el enlace oficial G3042 y verifica el
expediente por su referencia o por el codigo electronico exacto de su
resguardo. Se ha validado la consulta autenticada de E00006: Solicitado,
todavia sin certificado. La recogida final se verifica de nuevo por el PDF.

La version 2026.09.18.5 reconoce el formulario de recogida real observado
en G3042: fCodSolicitud y Enviar. La consulta se hace en nombre propio, sin
fechas predefinidas, y nunca usa los controles de validar o firmar solicitudes.

Las solicitudes antiguas marcadas completed no se reclasifican automaticamente:
requieren inspeccionar su PDF y confirmar el expediente sin emitir otro.

La consulta DEHu usa los ultimos 30 dias para comunicaciones y realizadas.
Las realizadas solo actualizan referencias ya controladas; no importan el
historico previo al alta. Nunca abre ni descarga documentos. Si una bandeja
falla, no se importa un resultado parcial; el error incluye el estado HTTP
cuando esta disponible.

Antes de arrancar, crear `secrets/aapp_worker_api_key.txt` con el mismo valor de
`AAPP_WORKER_API_KEY` configurado en Railway, sin comillas ni espacios.

```sh
docker compose config
docker compose -p gest2a3eco-aapp-worker-v3 up --build -d
docker compose ps
docker compose -p gest2a3eco-aapp-worker-v3 logs --tail=100 aapp-worker
```

Los certificados de cliente y sus contrasenas solo existen durante cada
tramite dentro del `tmpfs` del contenedor. Los diagnosticos se conservan en el
volumen `diagnostico/` y no deben contener el material criptografico.

La version 2026.09.18.8 usa el codigo electronico de 16 caracteres leido del
resguardo original para la recogida AEAT. Es distinto de la referencia
numerica/TCT. El worker solo puede descargar el resguardo del expediente
reclamado con su token vigente; no se duplican codigos en configuraciones.

La version 2026.09.21.1 exige NIF y razon social del contratante para AEAT,
detiene el tramite si no se identifican los controles de validacion o firma y
admite el boton final "Descargar documento". Requiere reconstruir la imagen.

La version 2026.09.22.1 cierra mediante "Continuar" el aviso informativo
inicial de AEAT que bloqueaba la seleccion del certificado generico y el boton
Validar solicitud. Si aparece un aviso despues de validar, detiene el tramite
para revisar la respuesta de AEAT antes de cualquier firma. Requiere
reconstruir la imagen; las solicitudes fallidas pueden reintentarse desde la app.

La version 2026.09.22.2 incorpora un diagnostico de solo lectura para DGT/DEV.
Ofrece al portal el certificado temporal del cliente, no pulsa acciones sobre
notificaciones y elimina la copia del PFX al terminar. Las capturas privadas se
usan para validar el conector antes de habilitar su sincronizacion general.

La version 2026.09.22.3 activa la consulta pasiva DGT/DEV ya validada con
E00006. Detecta expresamente los titulares no dados de alta, no abre ni acepta
avisos y envia al backend las filas visibles para mantener su historico y sus
cambios de estado.

La version 2026.09.23.1 reintenta automaticamente los buzones DEHu que fallen
en seis consultas escalonadas durante casi cuatro horas. El correo del lote no
se envia hasta que esas reconsultas terminan e indica los buzones reconsultados
y el numero de intentos utilizado por cada uno.
