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

// El backend envia WebpushNotification y fcm_options.link.
// Firebase muestra el aviso y abre la ruta correspondiente.
// Este handler se mantiene solo para diagnostico, sin mostrar otro aviso.
messaging.onBackgroundMessage((payload) => {
  console.debug('[FCM] Mensaje recibido en segundo plano', {
    messageId: payload.messageId || '',
  });
});
