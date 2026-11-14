const CACHE = 'family-math-ed49ac879ec1f2d6';
const STATIC = ['./','index.html','styles.css','scratchpad.css','stable-render.js','scratchpad.js','app.js','review-bank.js','daily-quotes.js','daily-checkin.js','daily-checkin.css','family-rewards.js','family-rewards.css','answer-fields.js','data.js','curriculum.js','learning-evidence.js','auto-refresh.js','manifest.webmanifest','assets/lucide.min.js','assets/icon.svg','assets/mushroom-garden.svg','assets/icon-180.png','assets/icon-192.png','assets/icon-512.png'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(STATIC)).then(() => self.skipWaiting())); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('family-math-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || new URL(event.request.url).origin !== self.location.origin) return;
  const url = new URL(event.request.url); const path = url.pathname.slice(new URL(self.registration.scope).pathname.length);
  if (path && !STATIC.includes(path)) return;
  event.respondWith(fetch(event.request).then(response => { if (response.ok) { const copy = response.clone(); event.waitUntil(caches.open(CACHE).then(cache => cache.put(event.request,copy))); } return response; }).catch(() => caches.match(event.request)));
});
