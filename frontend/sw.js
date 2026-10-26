const CACHE = 'cocheira-radames-v85';
const ASSETS = ['/', '/index.html', '/styles.css?v=85', '/api.js', '/app.js?v=85', '/lifecycle.js', '/quick-capture.js', '/horse.svg', '/icon-192.png', '/icon-512.png', '/icons/cruzas-microscopio.png', '/icons/potros-tropa-final-contorno-principal-2x.png?v=v4', '/icons/cavalo.png?v=v11-base-v6', '/icons/cavalo-treinamento-v6.png?v=v6', '/icons/polo-sem-dobras-camisa.png?v=v4', '/manifest.webmanifest'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS))); self.skipWaiting(); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))); self.clients.claim(); });
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || new URL(event.request.url).pathname.startsWith('/api/')) return;
  event.respondWith(fetch(event.request).then(response => { const copy = response.clone(); caches.open(CACHE).then(cache => cache.put(event.request, copy)); return response; }).catch(() => caches.match(event.request).then(hit => hit || caches.match('/index.html'))));
});
