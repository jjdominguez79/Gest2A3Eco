const CACHE='gestinem-messaging-v3';
const ASSETS=['/mensajes','/static/messaging.css','/static/messaging.js','/static/messaging.webmanifest','/static/gestinem-logo.png'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key))))));
self.addEventListener('fetch',event=>{if(event.request.method==='GET'&&new URL(event.request.url).origin===location.origin)event.respondWith(fetch(event.request).catch(()=>caches.match(event.request))) });
