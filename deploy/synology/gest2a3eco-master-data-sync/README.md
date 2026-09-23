# gest2a3eco-master-data-sync

Worker unidireccional de datos maestros: PostgreSQL del escritorio hacia el
backend Railway. Sincroniza empleados, empresas, clientes contables y la serie
`APP`. Las bajas de empleados revocan el acceso, pero nunca eliminan su
historial de mensajeria.

```sh
docker compose config
docker compose up --build -d
docker compose logs --tail=100 master-data-sync
```

## Orden de despliegue para empleados Entra

1. Desplegar primero el backend, que crea `msg_staff.desktop_user_id` y el
   endpoint de fotografia de empleados.
2. Actualizar y abrir al menos una vez la aplicacion de escritorio para crear
   las columnas Entra de `usuarios`.
3. Dar de alta los correos corporativos desde Administracion de usuarios. El
   usuario local `admin` queda excluido como cuenta de emergencia.
4. Desplegar o reiniciar este worker.
5. Publicar Flutter. La aplicacion solo lista personal activo y conserva alias,
   canales, avatar e historial en el backend.

El primer emparejamiento reutiliza por correo el UUID que ya exista en
`msg_staff`; nunca sustituye claves usadas por chats o mensajes.
