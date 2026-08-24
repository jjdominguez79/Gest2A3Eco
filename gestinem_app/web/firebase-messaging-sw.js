// Service worker para Firebase Cloud Messaging en Flutter Web.
//
// IMPORTANTE: Los valores PENDIENTE_* se sustituyen por tool/deploy_firebase.ps1
// antes de ejecutar "flutter build web". No rellenar manualmente.
//
// Convivencia con flutter_service_worker.js:
//   - Este SW solo gestiona mensajes FCM y clics de notificacion.
//   - No intercepta fetch ni gestiona cache (eso lo hace Flutter).

importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: 'PENDIENTE_FIREBASE_WEB_API_KEY',
  authDomain: 'PENDIENTE_FIREBASE_AUTH_DOMAIN',
  projectId: 'PENDIENTE_FIREBASE_PROJECT_ID',
  storageBucket: 'PENDIENTE_FIREBASE_STORAGE_BUCKET',
  messagingSenderId: 'PENDIENTE_FIREBASE_MESSAGING_SENDER_ID',
  appId: 'PENDIENTE_FIREBASE_APP_ID',
});

const messaging = firebase.messaging();

// onBackgroundMessage reemplaza el comportamiento por defecto de Firebase:
// mostramos una sola notificacion con tag para evitar duplicados.
messaging.onBackgroundMessage((payload) => {
  const data = payload.data || {};
  const notif = payload.notification || {};
  const title = notif.title || data.title || 'Gestinem';
  const body = notif.body || data.body || 'Tienes un nuevo mensaje';
  const conversationId = data.conversation_id || '';
  const threadId = data.thread_id || '';

  // tag unico por conversacion/hilo para colapsar notificaciones repetidas.
  const tag = conversationId || threadId || 'gestinem-msg';

  return self.registration.showNotification(title, {
    body,
    icon: '/icons/Icon-192.png',
    badge: '/icons/Icon-192.png',
    tag,
    data: { conversationId, threadId },
  });
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const d = event.notification.data || {};
  const conversationId = d.conversationId || '';
  const threadId = d.threadId || '';

  let url;
  if (conversationId) {
    url = 'https://app.gestinem.es/#/conversation/' + conversationId;
  } else if (threadId) {
    url = 'https://app.gestinem.es/#/internal/' + threadId;
  } else {
    url = 'https://app.gestinem.es/';
  }

  event.waitUntil(
    clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((windowClients) => {
        // Buscar una pestana existente del dominio.
        for (const client of windowClients) {
          if (
            (client.url.startsWith('https://app.gestinem.es') ||
              client.url.startsWith(self.location.origin)) &&
            'focus' in client
          ) {
            // Notificar a la app para que navegue a la conversacion.
            client.postMessage({
              type: 'fcm_notification_click',
              conversationId,
              threadId,
            });
            return client.focus();
          }
        }
        // No hay pestana abierta: abrir una nueva.
        return clients.openWindow(url);
      }),
  );
});
