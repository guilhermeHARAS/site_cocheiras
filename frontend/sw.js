const CACHE = 'cocheira-radames-v88';
const ASSETS = ['/', '/index.html', '/styles.css?v=88', '/api.js?v=88', '/app.js?v=88', '/lifecycle.js?v=88', '/quick-capture.js?v=88', '/horse.svg', '/icon-192.png', '/icon-512.png', '/icons/cruzas-microscopio.png?v=88', '/icons/potros-tropa-final-contorno-principal-2x.png?v=88', '/icons/cavalo.png?v=88', '/icons/cavalo-treinamento-v6.png?v=88', '/icons/polo-sem-dobras-camisa.png?v=88', '/manifest.webmanifest'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS))); self.skipWaiting(); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))); self.clients.claim(); });
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || new URL(event.request.url).pathname.startsWith('/api/')) return;
  const refresh = fetch(event.request).then(async response => {
    if (response.ok) {
      const cache = await caches.open(CACHE);
      await cache.put(event.request, response.clone());
    }
    return response;
  });
  event.waitUntil(refresh.then(() => undefined).catch(() => undefined));
  event.respondWith(caches.match(event.request).then(hit => hit || refresh).catch(() => caches.match('/index.html')));
});
